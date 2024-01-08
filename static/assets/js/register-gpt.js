let submitButton = document.querySelector("button");
let errorDiv = document.getElementById("error");

async function postGPTApp(data) {
  try {
    let response = await fetch("/api/v1/custom-gpt-application", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    });
    let errorString;
    if (response.ok) {
      window.location.href = "/";
      return;
    } else if (response.status === 422) {
      let errorJson = (await response.json()).detail[0];
      errorString = errorJson.loc[1].split("_").join(" ");
      errorString = `${errorString} : ${errorJson.msg}`;
    } else if (response.status === 409) {
      let errorJson = await response.json();
      errorString = errorJson.detail;
    }
    errorDiv.innerText = errorString;
    errorDiv.classList.add("alert");
    errorDiv.classList.add("alert-danger");
    errorDiv.style.display = "block";
  } catch (e) {
    console.log(e);
  }
}
submitButton.addEventListener("click", async (e) => {
  e.preventDefault();
  let gptName = document.getElementById("gpt-name").value;
  let gptDescription = document.getElementById("gpt-description").value;
  let gptUrl = document.getElementById("gpt-url").value;
  await postGPTApp({
    gpt_name: gptName,
    gpt_url: gptUrl,
    gpt_description: gptDescription,
    verification_medium: "Google",
  });
});
