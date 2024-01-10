let gptName = document.getElementById("gpt-name");
let gptUrl = document.getElementById("gpt-url");
let verificationMedium = document.getElementById("verification-medium");
let gptDescription = document.getElementById("gpt-description");
let uuid = document.getElementById("uuid");
let privacyPolicyUrl = document.getElementById("privacy-policy-url");
let prompt = document.getElementById("prompt");
let actionSchemaUrl = document.getElementById("action-schema-url");
let created = document.getElementById("created-at");
let clientId = document.getElementById("client-id");
let clientSecret = document.getElementById("client-secret");
let authorizationUrl = document.getElementById("authorization-url");
let tokenUrl = document.getElementById("token-url");
let scope = document.getElementById("scope");
let authenticationType = document.getElementById("authentication-type");
let tokenExchangeMethod = document.getElementById("token-exchange-method");

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
    gptName.textContent = data.gpt_name;
    gptUrl.textContent = data.gpt_url;
    verificationMedium.textContent = data.verification_medium;
    gptDescription.textContent = data.gpt_description;
    uuid.textContent = data.uuid;
    privacyPolicyUrl.textContent = data.privacy_policy_url;
    prompt.textContent = data.prompt;
    actionSchemaUrl.textContent = data.action_schema_url;

    let createdAt = moment(data.created_at);
    created.title = createdAt.format("YYYY-MM-DD HH:mm:ss");
    created.textContent = createdAt.fromNow();

    clientId.textContent = data.authentication_details.client_id;
    clientSecret.textContent = data.authentication_details.client_secret;
    authorizationUrl.textContent =
      data.authentication_details.authorization_url;
    tokenUrl.textContent = data.authentication_details.token_url;
    scope.textContent = data.authentication_details.scope;
    authenticationType.textContent =
      data.authentication_details.authentication_type;
    tokenExchangeMethod.textContent =
      data.authentication_details.token_exchange_method;
  } catch (error) {
    console.error("Error fetching data:", error);
  }
}

fetchGPTApplicationDetails();
