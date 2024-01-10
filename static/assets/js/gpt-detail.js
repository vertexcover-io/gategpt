let gptName = document.getElementById("gpt-name");
let gptUrl = document.getElementById("gpt-url");
let verificationMedium = document.getElementById("verification-medium");
let gptDescription = document.getElementById("gpt-description");
let uuid = document.getElementById("uuid");
let privacyPolicyUrl = document.getElementById("privacy-policy-url");
let gptPrompt = document.getElementById("prompt");
let actionSchemaUrl = document.getElementById("action-schema-url");
let created = document.getElementById("created-at");
let clientId = document.getElementById("client-id");
let clientSecret = document.getElementById("client-secret");
let authorizationUrl = document.getElementById("authorization-url");
let tokenUrl = document.getElementById("token-url");
let scope = document.getElementById("scope");
let authenticationType = document.getElementById("authentication-type");
let tokenExchangeMethod = document.getElementById("token-exchange-method");
let appSessionsLink = document.getElementById("app-sessions-link");
let pageTitle = document.getElementById("page-title");

let url = new URL(window.location.href);
let pathSegments = url.pathname.split("/");
let gptApplicationId = pathSegments[pathSegments.length - 1];

function createAnchor(value) {
  let a = document.createElement("a");
  a.href = value;
  a.textContent = value;
  return a;
}
function createCopyButton(value) {
  let img = document.createElement("img");
  img.src = "/static/assets/images/copy.svg";
  img.height = "30";
  img.width = "30";
  img.style.cursor = "pointer";
  img.addEventListener("click", () => {
    navigator.clipboard.writeText(value);
  });
  return img;
}

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
    gptName.textContent = data.gpt_name;
    pageTitle.textContent = data.gpt_name;
    gptUrl.appendChild(createAnchor(data.gpt_url));
    verificationMedium.textContent = data.verification_medium;
    gptDescription.textContent = data.gpt_description;
    uuid.textContent = data.uuid;

    privacyPolicyUrl.appendChild(createAnchor(data.privacy_policy_url));

    gptPrompt.textContent = data.prompt;
    actionSchemaUrl.textContent = data.action_schema_url;

    let createdAt = moment(data.created_at);
    created.title = createdAt.format("YYYY-MM-DD HH:mm:ss");
    created.textContent = createdAt.fromNow();

    clientId.textContent = data.authentication_details.client_id;
    clientId.appendChild(
      createCopyButton(data.authentication_details.client_id),
    );

    clientSecret.textContent = data.authentication_details.client_secret;
    clientSecret.appendChild(
      createCopyButton(data.authentication_details.client_secret),
    );

    authorizationUrl.textContent =
      data.authentication_details.authorization_url;

    tokenUrl.textContent = data.authentication_details.token_url;
    scope.textContent = data.authentication_details.scope;
    authenticationType.textContent =
      data.authentication_details.authentication_type;
    tokenExchangeMethod.textContent =
      data.authentication_details.token_exchange_method;

    appSessionsLink.href = `/custom-gpt-application/${gptApplicationId}/gpt-app-sessions/`;
  } catch (error) {
    console.error("Error fetching data:", error);
  }
}

fetchGPTApplicationDetails();
