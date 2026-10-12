document.querySelectorAll("[data-password-visibility]").forEach((button) => {
  const input = document.getElementById(button.getAttribute("aria-controls"));
  if (!input) return;

  button.addEventListener("click", () => {
    const reveal = input.type === "password";
    input.type = reveal ? "text" : "password";
    button.setAttribute("aria-pressed", String(reveal));
    button.setAttribute("aria-label", reveal ? "Hide password" : "Show password");
    button.title = reveal ? "Hide password" : "Show password";
    button.querySelector(".password-visibility-show").hidden = reveal;
    button.querySelector(".password-visibility-hide").hidden = !reveal;
  });
});
