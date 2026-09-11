from contextlib import asynccontextmanager
from datetime import date
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse
import hashlib, json, re, secrets, time, uuid

from botocore.exceptions import ClientError
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import qrcode
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import __version__
from app.db import engine, get_db
from app.models import ArchiveJob, Event, Media, User, UserSession
from app.security import hash_password, new_session, user_from_session_token, verify_password
from app.services.storage import bucket_is_ready, create_presigned_download, create_presigned_upload, delete_objects, ensure_bucket, head_object
from app.settings import settings

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates")); SESSION_COOKIE = "markmonica_session"
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/heic", "image/heif"}; ALLOWED_VIDEO_TYPES = {"video/mp4", "video/quicktime", "video/x-m4v", "video/webm"}
ALLOWED_COVER_TYPES={"image/jpeg","image/png","image/webp"}; MAX_COVER_BYTES=15*1024*1024
ALLOWED_EVENT_THEMES={"classic","romantic","modern"}; DEFAULT_ACCENT_COLOR="#7c5cff"
ALLOWED_GUEST_FONTS={"default","playfair","cormorant","dm-serif","great-vibes","parisienne","dancing-script","libre-baskerville","montserrat","poppins"}

def origin_for(url):
    if not url: return None
    parsed=urlparse(url); return f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else None
APP_ORIGIN=origin_for(settings.app_url); STORAGE_ORIGIN=origin_for(settings.s3_public_endpoint_url or settings.s3_endpoint_url); COOKIE_SECURE=bool(APP_ORIGIN and APP_ORIGIN.startswith("https://"))

class UploadRequest(BaseModel): filename:str; content_type:str; size_bytes:int; guest_name:str|None=None
class UploadConfirmRequest(BaseModel): media_id:uuid.UUID
class CoverUploadRequest(BaseModel): filename:str; content_type:str; size_bytes:int
class CoverConfirmRequest(BaseModel): object_key:str; content_type:str; size_bytes:int
class MediaIdsRequest(BaseModel): media_ids:list[uuid.UUID]
class ArchiveRequest(BaseModel): media_ids:list[uuid.UUID]|None=None

@asynccontextmanager
async def lifespan(_:FastAPI):
    if settings.s3_auto_create_bucket: ensure_bucket()
    yield
app=FastAPI(title=settings.app_name,version=__version__,lifespan=lifespan); app.mount("/static",StaticFiles(directory=str(BASE_DIR/"static")),name="static")

@app.middleware("http")
async def security_headers(request,call_next):
    response=await call_next(request); storage=f" {STORAGE_ORIGIN}" if STORAGE_ORIGIN else ""
    response.headers.setdefault("X-Content-Type-Options","nosniff"); response.headers.setdefault("X-Frame-Options","DENY"); response.headers.setdefault("Referrer-Policy","strict-origin-when-cross-origin"); response.headers.setdefault("Permissions-Policy","camera=(), microphone=(), geolocation=()"); response.headers.setdefault("Content-Security-Policy","default-src 'self'; "+f"img-src 'self' data:{storage}; "+f"media-src 'self'{storage}; "+f"connect-src 'self'{storage}; "+"style-src 'self' https://fonts.googleapis.com; script-src 'self'; font-src 'self' https://fonts.gstatic.com; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
    if COOKIE_SECURE: response.headers.setdefault("Strict-Transport-Security","max-age=31536000; includeSubDomains")
    return response

def current_user(request,db): return user_from_session_token(db,request.cookies.get(SESSION_COOKIE))
def require_same_origin(request):
    if not APP_ORIGIN:return
    origin=request.headers.get("origin")
    if origin:
        if origin.rstrip("/")!=APP_ORIGIN.rstrip("/"):raise HTTPException(403,"Cross-site request rejected.")
        return
    referer=request.headers.get("referer")
    if not referer or not referer.startswith(f"{APP_ORIGIN.rstrip('/')}/"):raise HTTPException(403,"Request origin could not be verified.")
def client_ip(request):
    forwarded=request.headers.get("x-forwarded-for",""); return (forwarded.split(",",1)[0].strip() if forwarded else (request.client.host if request.client else "unknown"))[:64]
def enforce_guest_upload_rate_limit(request,slug):
    limit=settings.guest_upload_rate_limit_per_minute
    if limit<=0:return
    key=f"markmonica:rate:upload:{slug}:{client_ip(request)}:{int(time.time()//60)}"
    try:
        redis=Redis.from_url(settings.redis_url,socket_connect_timeout=1,socket_timeout=1); count=redis.incr(key)
        if count==1:redis.expire(key,120)
        if count>limit:raise HTTPException(429,"Too many upload attempts. Please wait a moment and try again.")
    except HTTPException:raise
    except RedisError:return
def enqueue(job):
    try: Redis.from_url(settings.redis_url,socket_connect_timeout=1,socket_timeout=1,decode_responses=True).rpush(settings.worker_queue,json.dumps(job))
    except RedisError: pass
def enqueue_media_processing(media_id): enqueue({"type":"process_media","media_id":str(media_id)})
def slugify(value): return re.sub(r"[^a-z0-9]+","-",value.lower()).strip("-")[:90] or "event"
def safe_filename(value): return re.sub(r"[^A-Za-z0-9._-]+","-",Path(value).name).strip("-.")[:180] or "upload"
def clean_message(value,max_length=1200): return (value or "").strip()[:max_length] or None
def clean_accent_color(value):
    value=(value or "").strip()
    return value.lower() if re.fullmatch(r"#[0-9a-fA-F]{6}",value) else DEFAULT_ACCENT_COLOR
def event_for_owner(db,user,event_id):
    event=db.scalar(select(Event).where(Event.id==event_id,Event.owner_id==user.id))
    if event is None:raise HTTPException(404)
    return event
def live_event_by_slug(db,slug):
    event=db.scalar(select(Event).where(Event.slug==slug))
    if event is None:raise HTTPException(404)
    if event.status!="live":raise HTTPException(403,"This event is not accepting uploads yet.")
    return event
def guest_url(event):return f"{settings.app_url.rstrip('/')}/e/{event.slug}"
def validate_upload(content_type,size_bytes):
    if size_bytes<=0:raise HTTPException(400,"Empty files cannot be uploaded.")
    if content_type in ALLOWED_IMAGE_TYPES:limit=settings.max_image_upload_mb*1024*1024
    elif content_type in ALLOWED_VIDEO_TYPES:limit=settings.max_video_upload_mb*1024*1024
    else:raise HTTPException(415,"This photo or video format is not supported.")
    if size_bytes>limit:raise HTTPException(413,"This file is larger than the event upload limit.")
def validate_cover(content_type,size_bytes):
    if content_type not in ALLOWED_COVER_TYPES:raise HTTPException(415,"Cover photos must be JPG, PNG or WebP.")
    if size_bytes<=0:raise HTTPException(400,"Empty files cannot be uploaded.")
    if size_bytes>MAX_COVER_BYTES:raise HTTPException(413,"Cover photos must be 15 MB or smaller.")
def set_session_cookie(response,token):response.set_cookie(SESSION_COOKIE,token,httponly=True,secure=COOKIE_SECURE,samesite="lax",max_age=30*86400,path="/")

@app.get("/health")
def health():return {"status":"ok","app":settings.app_name,"version":__version__}
@app.get("/health/ready")
def readiness():
    checks={"database":False,"redis":False,"storage":False}
    try:
        with engine.connect() as connection:connection.execute(text("SELECT 1"));checks["database"]=True
    except Exception:pass
    try:checks["redis"]=bool(Redis.from_url(settings.redis_url,socket_connect_timeout=2,socket_timeout=2).ping())
    except Exception:pass
    checks["storage"]=bucket_is_ready();ready=all(checks.values());return JSONResponse({"status":"ready" if ready else "degraded","checks":checks},status_code=200 if ready else 503)
@app.get("/",response_class=HTMLResponse)
def home(request:Request):return templates.TemplateResponse(request=request,name="index.html",context={"app_name":settings.app_name,"version":__version__,"user":None})
@app.get("/register",response_class=HTMLResponse)
def register_page(request:Request):return templates.TemplateResponse(request=request,name="register.html",context={"error":None})
@app.post("/register")
def register(request:Request,display_name:str=Form(...),email:str=Form(...),password:str=Form(...),db:Session=Depends(get_db)):
    require_same_origin(request);email=email.strip().lower();display_name=display_name.strip()
    if len(password)<8 or not display_name or "@" not in email:return templates.TemplateResponse(request=request,name="register.html",context={"error":"Please enter a name, valid email address and a password of at least 8 characters."},status_code=400)
    user=User(email=email,display_name=display_name,password_hash=hash_password(password));db.add(user)
    try:db.commit();db.refresh(user)
    except IntegrityError:db.rollback();return templates.TemplateResponse(request=request,name="register.html",context={"error":"An account with that email address already exists."},status_code=409)
    _,token=new_session(db,user);response=RedirectResponse("/dashboard",303);set_session_cookie(response,token);return response
@app.get("/login",response_class=HTMLResponse)
def login_page(request:Request):return templates.TemplateResponse(request=request,name="login.html",context={"error":None})
@app.post("/login")
def login(request:Request,email:str=Form(...),password:str=Form(...),db:Session=Depends(get_db)):
    require_same_origin(request);user=db.scalar(select(User).where(User.email==email.strip().lower(),User.is_active.is_(True)))
    if user is None or not verify_password(password,user.password_hash):return templates.TemplateResponse(request=request,name="login.html",context={"error":"Incorrect email address or password."},status_code=401)
    _,token=new_session(db,user);response=RedirectResponse("/dashboard",303);set_session_cookie(response,token);return response
@app.post("/logout")
def logout(request:Request,db:Session=Depends(get_db)):
    require_same_origin(request);token=request.cookies.get(SESSION_COOKIE)
    if token:
        session=db.scalar(select(UserSession).where(UserSession.token_hash==hashlib.sha256(token.encode()).hexdigest()))
        if session:db.delete(session);db.commit()
    response=RedirectResponse("/",303);response.delete_cookie(SESSION_COOKIE,path="/");return response
@app.get("/dashboard",response_class=HTMLResponse)
def dashboard(request:Request,db:Session=Depends(get_db)):
    user=current_user(request,db)
    if user is None:return RedirectResponse("/login",303)
    events=db.scalars(select(Event).where(Event.owner_id==user.id).order_by(Event.created_at.desc())).all();return templates.TemplateResponse(request=request,name="dashboard.html",context={"user":user,"events":events,"today":date.today(),"error":None})
@app.post("/events")
def create_event(request:Request,title:str=Form(...),event_date:str=Form(""),db:Session=Depends(get_db)):
    require_same_origin(request);user=current_user(request,db)
    if user is None:return RedirectResponse("/login",303)
    title=title.strip()
    if not title:return RedirectResponse("/dashboard",303)
    try:parsed_date=date.fromisoformat(event_date) if event_date else None
    except ValueError:parsed_date=None
    event=Event(owner_id=user.id,title=title,event_date=parsed_date,slug=f"{slugify(title)}-{secrets.token_hex(3)}");db.add(event);db.commit();db.refresh(event);return RedirectResponse(f"/events/{event.id}",303)
@app.get("/events/{event_id}",response_class=HTMLResponse)
def manage_event(event_id:str,request:Request,db:Session=Depends(get_db)):
    user=current_user(request,db)
    if user is None:return RedirectResponse("/login",303)
    event=event_for_owner(db,user,event_id);media=db.scalars(select(Media).where(Media.event_id==event.id,Media.status=="uploaded").order_by(Media.created_at.desc())).all();return templates.TemplateResponse(request=request,name="event_manage.html",context={"user":user,"event":event,"guest_url":guest_url(event),"media":media})
@app.post("/events/{event_id}")
def update_event(event_id:str,request:Request,title:str=Form(...),event_date:str=Form(""),status:str=Form("draft"),welcome_message:str=Form(""),thank_you_message:str=Form(""),theme:str=Form("classic"),accent_color:str=Form(DEFAULT_ACCENT_COLOR),guest_font:str=Form("default"),guest_gallery_enabled:str|None=Form(None),db:Session=Depends(get_db)):
    require_same_origin(request);user=current_user(request,db)
    if user is None:return RedirectResponse("/login",303)
    event=event_for_owner(db,user,event_id);event.title=title.strip() or event.title
    try:event.event_date=date.fromisoformat(event_date) if event_date else None
    except ValueError:pass
    event.status="live" if status=="live" else "draft";event.welcome_message=clean_message(welcome_message);event.thank_you_message=clean_message(thank_you_message);event.theme=theme if theme in ALLOWED_EVENT_THEMES else "classic";event.accent_color=clean_accent_color(accent_color);event.guest_font=guest_font if guest_font in ALLOWED_GUEST_FONTS else "default";event.guest_gallery_enabled=guest_gallery_enabled is not None;db.commit();return RedirectResponse(f"/events/{event.id}",303)
@app.get("/events/{event_id}/qr.png")
def event_qr(event_id:str,request:Request,db:Session=Depends(get_db)):
    user=current_user(request,db)
    if user is None:raise HTTPException(401)
    event=event_for_owner(db,user,event_id);image=qrcode.make(guest_url(event));output=BytesIO();image.save(output,format="PNG");return Response(output.getvalue(),media_type="image/png",headers={"Content-Disposition":f'inline; filename="{event.slug}-qr.png"'})
@app.post("/api/events/{event_id}/cover")
def initiate_cover(event_id:uuid.UUID,payload:CoverUploadRequest,request:Request,db:Session=Depends(get_db)):
    require_same_origin(request);user=current_user(request,db)
    if user is None:raise HTTPException(401)
    event=event_for_owner(db,user,event_id);content_type=payload.content_type.lower().strip();validate_cover(content_type,payload.size_bytes);ext={"image/jpeg":"jpg","image/png":"png","image/webp":"webp"}[content_type];object_key=f"events/{event.id}/cover/{uuid.uuid4().hex}.{ext}";return {"object_key":object_key,"upload_url":create_presigned_upload(object_key,content_type),"content_type":content_type}
@app.post("/api/events/{event_id}/cover/confirm")
def confirm_cover(event_id:uuid.UUID,payload:CoverConfirmRequest,request:Request,db:Session=Depends(get_db)):
    require_same_origin(request);user=current_user(request,db)
    if user is None:raise HTTPException(401)
    event=event_for_owner(db,user,event_id);content_type=payload.content_type.lower().strip();validate_cover(content_type,payload.size_bytes);prefix=f"events/{event.id}/cover/"
    if not payload.object_key.startswith(prefix):raise HTTPException(400,"Invalid cover object.")
    try:uploaded=head_object(payload.object_key)
    except ClientError as exc:raise HTTPException(409,"The cover photo could not be verified yet.") from exc
    if int(uploaded.get("ContentLength",0))!=payload.size_bytes:raise HTTPException(409,"The uploaded cover does not match the requested file.")
    actual_type=str(uploaded.get("ContentType","")).lower()
    if actual_type and actual_type!=content_type:raise HTTPException(409,"The uploaded cover has an unexpected content type.")
    previous=event.cover_object_key;event.cover_object_key=payload.object_key;event.cover_content_type=content_type;db.commit()
    if previous and previous!=payload.object_key:
        try:delete_objects([previous])
        except Exception:pass
    return {"status":"ready","cover_url":f"/events/{event.id}/cover"}
@app.delete("/api/events/{event_id}/cover")
def remove_cover(event_id:uuid.UUID,request:Request,db:Session=Depends(get_db)):
    require_same_origin(request);user=current_user(request,db)
    if user is None:raise HTTPException(401)
    event=event_for_owner(db,user,event_id);key=event.cover_object_key
    if key:
        try:delete_objects([key])
        except Exception as exc:raise HTTPException(502,"Could not remove the cover photo from storage.") from exc
    event.cover_object_key=None;event.cover_content_type=None;db.commit();return {"status":"removed"}
@app.get("/events/{event_id}/cover")
def host_cover(event_id:uuid.UUID,request:Request,db:Session=Depends(get_db)):
    user=current_user(request,db)
    if user is None:raise HTTPException(401)
    event=event_for_owner(db,user,event_id)
    if not event.cover_object_key:raise HTTPException(404)
    return RedirectResponse(create_presigned_download(event.cover_object_key),302)
@app.get("/e/{event_slug}/cover")
def guest_cover(event_slug:str,db:Session=Depends(get_db)):
    event=live_event_by_slug(db,event_slug)
    if not event.cover_object_key:raise HTTPException(404)
    return RedirectResponse(create_presigned_download(event.cover_object_key),302)
@app.get("/e/{event_slug}",response_class=HTMLResponse)
def guest_event(event_slug:str,request:Request,db:Session=Depends(get_db)):
    event=live_event_by_slug(db,event_slug);guest_media=[]
    if event.guest_gallery_enabled:guest_media=db.scalars(select(Media).where(Media.event_id==event.id,Media.status=="uploaded",Media.processing_status=="ready").order_by(Media.created_at.desc())).all()
    return templates.TemplateResponse(request=request,name="guest_event.html",context={"event":event,"guest_media":guest_media,"max_image_mb":settings.max_image_upload_mb,"max_video_mb":settings.max_video_upload_mb})
@app.post("/api/events/{event_slug}/uploads")
def initiate_upload(event_slug:str,payload:UploadRequest,request:Request,db:Session=Depends(get_db)):
    enforce_guest_upload_rate_limit(request,event_slug);event=live_event_by_slug(db,event_slug);content_type=payload.content_type.lower().strip();validate_upload(content_type,payload.size_bytes);filename=safe_filename(payload.filename);object_key=f"events/{event.id}/originals/{uuid.uuid4().hex}-{filename}";media=Media(event_id=event.id,object_key=object_key,original_filename=filename,content_type=content_type,size_bytes=payload.size_bytes,uploader_name=(payload.guest_name or "").strip()[:160] or None,status="pending",processing_status="pending");db.add(media);db.commit();db.refresh(media);return {"media_id":str(media.id),"object_key":object_key,"upload_url":create_presigned_upload(object_key,content_type),"content_type":content_type,"max_bytes":settings.max_video_upload_mb*1024*1024 if content_type in ALLOWED_VIDEO_TYPES else settings.max_image_upload_mb*1024*1024}
@app.post("/api/events/{event_slug}/uploads/confirm")
def confirm_upload(event_slug:str,payload:UploadConfirmRequest,request:Request,db:Session=Depends(get_db)):
    event=live_event_by_slug(db,event_slug);media=db.scalar(select(Media).where(Media.id==payload.media_id,Media.event_id==event.id))
    if media is None:raise HTTPException(404)
    if media.status=="uploaded":return {"status":"uploaded","media_id":str(media.id),"processing_status":media.processing_status}
    try:uploaded=head_object(media.object_key)
    except ClientError as exc:raise HTTPException(409,"The uploaded file could not be verified yet.") from exc
    if int(uploaded.get("ContentLength",0))!=media.size_bytes:raise HTTPException(409,"The uploaded file does not match the requested file.")
    actual_type=str(uploaded.get("ContentType","")).lower()
    if actual_type and actual_type!=media.content_type.lower():raise HTTPException(409,"The uploaded file has an unexpected content type.")
    media.status="uploaded";media.processing_status="pending";db.commit();enqueue_media_processing(media.id);return {"status":"uploaded","media_id":str(media.id),"processing_status":media.processing_status}
@app.get("/events/{event_id}/media/{media_id}/preview")
def host_media_preview(event_id:uuid.UUID,media_id:uuid.UUID,request:Request,db:Session=Depends(get_db)):
    user=current_user(request,db)
    if user is None:raise HTTPException(401)
    event=event_for_owner(db,user,event_id);media=db.scalar(select(Media).where(Media.id==media_id,Media.event_id==event.id,Media.status=="uploaded"))
    if media is None:raise HTTPException(404)
    key=media.preview_object_key or media.poster_object_key or media.object_key;return RedirectResponse(create_presigned_download(key),302)
@app.get("/events/{event_id}/media/{media_id}/play")
def host_media_play(event_id:uuid.UUID,media_id:uuid.UUID,request:Request,db:Session=Depends(get_db)):
    user=current_user(request,db)
    if user is None:raise HTTPException(401)
    event=event_for_owner(db,user,event_id);media=db.scalar(select(Media).where(Media.id==media_id,Media.event_id==event.id,Media.status=="uploaded"))
    if media is None:raise HTTPException(404)
    key=media.processed_object_key or media.object_key;return RedirectResponse(create_presigned_download(key),302)
@app.get("/e/{event_slug}/media/{media_id}/preview")
def guest_media_preview(event_slug:str,media_id:uuid.UUID,db:Session=Depends(get_db)):
    event=live_event_by_slug(db,event_slug)
    if not event.guest_gallery_enabled:raise HTTPException(404)
    media=db.scalar(select(Media).where(Media.id==media_id,Media.event_id==event.id,Media.status=="uploaded",Media.processing_status=="ready"))
    if media is None:raise HTTPException(404)
    key=media.preview_object_key or media.poster_object_key
    if not key and media.content_type.startswith("image/"):key=media.object_key
    if not key:raise HTTPException(404)
    return RedirectResponse(create_presigned_download(key),302)
@app.get("/e/{event_slug}/media/{media_id}/play")
def guest_media_play(event_slug:str,media_id:uuid.UUID,db:Session=Depends(get_db)):
    event=live_event_by_slug(db,event_slug)
    if not event.guest_gallery_enabled:raise HTTPException(404)
    media=db.scalar(select(Media).where(Media.id==media_id,Media.event_id==event.id,Media.status=="uploaded",Media.processing_status=="ready"))
    if media is None or not media.content_type.startswith("video/") or not media.processed_object_key:raise HTTPException(404)
    return RedirectResponse(create_presigned_download(media.processed_object_key),302)
@app.get("/events/{event_id}/media/{media_id}/download")
def host_media_download(event_id:uuid.UUID,media_id:uuid.UUID,request:Request,db:Session=Depends(get_db)):
    user=current_user(request,db)
    if user is None:raise HTTPException(401)
    event=event_for_owner(db,user,event_id);media=db.scalar(select(Media).where(Media.id==media_id,Media.event_id==event.id,Media.status=="uploaded"))
    if media is None:raise HTTPException(404)
    return RedirectResponse(create_presigned_download(media.object_key),302,headers={"Content-Disposition":f'attachment; filename="{safe_filename(media.original_filename)}"'})
@app.post("/api/events/{event_id}/media/delete")
def delete_media(event_id:uuid.UUID,payload:MediaIdsRequest,request:Request,db:Session=Depends(get_db)):
    require_same_origin(request);user=current_user(request,db)
    if user is None:raise HTTPException(401)
    event=event_for_owner(db,user,event_id);ids=list(dict.fromkeys(payload.media_ids))
    if not ids:raise HTTPException(400,"Choose at least one item to delete.")
    media_items=db.scalars(select(Media).where(Media.event_id==event.id,Media.id.in_(ids))).all()
    if len(media_items)!=len(ids):raise HTTPException(404,"One or more selected items could not be found.")
    keys=[]
    for item in media_items:keys.extend(k for k in [item.object_key,item.preview_object_key,item.poster_object_key,item.processed_object_key] if k)
    try:delete_objects(keys)
    except Exception as exc:raise HTTPException(502,"Could not delete all selected files from storage.") from exc
    for item in media_items:db.delete(item)
    db.commit();return {"status":"deleted","deleted":len(media_items)}
@app.post("/api/events/{event_id}/archives")
def create_archive_job(event_id:uuid.UUID,payload:ArchiveRequest,request:Request,db:Session=Depends(get_db)):
    require_same_origin(request);user=current_user(request,db)
    if user is None:raise HTTPException(401)
    event=event_for_owner(db,user,event_id);requested=None
    if payload.media_ids:
        requested=list(dict.fromkeys(payload.media_ids));found=db.scalars(select(Media.id).where(Media.event_id==event.id,Media.status=="uploaded",Media.id.in_(requested))).all()
        if len(found)!=len(requested):raise HTTPException(404,"One or more selected items could not be found.")
    job=ArchiveJob(event_id=event.id,requested_media_ids=json.dumps([str(x) for x in requested]) if requested else None,status="queued",filename=f"{event.slug}-memories.zip");db.add(job);db.commit();db.refresh(job);enqueue({"type":"build_archive","archive_job_id":str(job.id)});return {"job_id":str(job.id),"status":job.status}
@app.get("/api/events/{event_id}/archives/{job_id}")
def archive_status(event_id:uuid.UUID,job_id:uuid.UUID,request:Request,db:Session=Depends(get_db)):
    user=current_user(request,db)
    if user is None:raise HTTPException(401)
    event=event_for_owner(db,user,event_id);job=db.scalar(select(ArchiveJob).where(ArchiveJob.id==job_id,ArchiveJob.event_id==event.id))
    if job is None:raise HTTPException(404)
    return {"job_id":str(job.id),"status":job.status,"error":job.error,"download_url":f"/events/{event.id}/archives/{job.id}/download" if job.status=="ready" else None}
@app.get("/events/{event_id}/archives/{job_id}/download")
def archive_download(event_id:uuid.UUID,job_id:uuid.UUID,request:Request,db:Session=Depends(get_db)):
    user=current_user(request,db)
    if user is None:raise HTTPException(401)
    event=event_for_owner(db,user,event_id);job=db.scalar(select(ArchiveJob).where(ArchiveJob.id==job_id,ArchiveJob.event_id==event.id,ArchiveJob.status=="ready"))
    if job is None or not job.object_key:raise HTTPException(404)
    return RedirectResponse(create_presigned_download(job.object_key),302,headers={"Content-Disposition":f'attachment; filename="{safe_filename(job.filename)}"'})
