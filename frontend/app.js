const configuredApi =
  window.VOXORA_API_URL || "https://voxora-gemini-voice-api.onrender.com";
const serviceLabel = document.querySelector("#service-label");
const callForm = document.querySelector("#call-form");
const callStatus = document.querySelector("#call-status");

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

callForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = callForm.elements.phone_number;
  const button = callForm.querySelector("button");
  const phoneNumber = input.value.trim();
  button.disabled = true;
  callStatus.textContent = "Connecting your call…";
  callStatus.className = "is-loading";
  try {
    const response = await fetch(`${configuredApi}/call`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ phone_number: phoneNumber }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Unable to start the call.");
    callStatus.textContent = data.message;
    callStatus.className = "is-success";
    input.value = "";
  } catch (error) {
    callStatus.textContent = error.message;
    callStatus.className = "is-error";
  } finally {
    button.disabled = false;
  }
});

document.querySelectorAll(".call-controls button").forEach((button) => {
  button.addEventListener("click", () => {
    button.animate(
      [{ transform: "scale(1)" }, { transform: "scale(.9)" }, { transform: "scale(1)" }],
      { duration: 240 }
    );
  });
});
