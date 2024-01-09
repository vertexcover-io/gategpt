let gptNameElement = document.getElementById("gpt-name");
let gptDescriptionElement = document.getElementById("gpt-description");
let gptUrlElement = document.getElementById("gpt-url");
let gptTokenExpiryElement = document.getElementById("gpt-token-expiry");
let gptCreatedAtElement = document.getElementById("gpt-created-at");
let gptUpdatedAtElement = document.getElementById("gpt-updated-at");
let clientIdElement = document.getElementById("client-id");
let clientSecretElement = document.getElementById("gpt-client-secret");
let titleName = document.getElementById("page-title");
let appSessions = document.getElementById("app-sessions-link");

let url = new URL(window.location.href);
let pathSegments = url.pathname.split("/");
let gptApplicationId = pathSegments[pathSegments.length - 1];

async function fetchGPTApplicationDetails() {
  try {
    let apiEndpoint = `/api/v1/custom-gpt-application/${gptApplicationId}`;

    let response = await fetch(apiEndpoint);
    if (!response.ok) {
      console.log(`HTTP error! status: ${response.status}`);
      return;
    }
    if (response.status === 404) {
      window.location.href = "/404";
      return;
    }

    let data = await response.json();
    titleName.textContent = data.gpt_name;
    gptNameElement.textContent = data.gpt_name;
    gptDescriptionElement.textContent = data.gpt_description;
    gptUrlElement.textContent = data.gpt_url;
    gptTokenExpiryElement.textContent = data.token_expiry;
    gptCreatedAtElement.textContent = data.created_at;
    gptUpdatedAtElement.textContent = data.updated_at;
    clientIdElement.textContent = data.client_id;
    clientSecretElement.textContent = data.client_secret;
    appSessions.href = `/custom-gpt-application/${gptApplicationId}/gpt-app-sessions/`;
  } catch (error) {
    console.error("Error fetching data:", error);
  }
}

fetchGPTApplicationDetails();
