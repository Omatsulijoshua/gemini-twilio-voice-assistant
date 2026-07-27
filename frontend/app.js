const configuredApi =
  window.VOXORA_API_URL || "https://voxora-gemini-voice-api.onrender.com";
const serviceLabel = document.querySelector("#service-label");

if (configuredApi && serviceLabel) {
  fetch(`${configuredApi.replace(/\/$/, "")}/health`)
    .then((response) => {
      if (!response.ok) throw new Error("Service unavailable");
      serviceLabel.textContent = "Online and healthy";
    })
    .catch(() => {
      serviceLabel.textContent = "Temporarily unavailable";
      serviceLabel.closest(".service-status").classList.add("offline");
    });
}

document.querySelectorAll(".call-controls button").forEach((button) => {
  button.addEventListener("click", () => {
    button.animate(
      [{ transform: "scale(1)" }, { transform: "scale(.9)" }, { transform: "scale(1)" }],
      { duration: 240 }
    );
  });
});
