import { getUser } from "./main.js";

let h1 = document.getElementById("welcome-h1");
(async function () {
  try {
    let user = await getUser();
    h1.innerText += ` ${user.name}`;
  } catch (e) {
    console.error("Error fetching user:", e);
  }
})();

async function fetchGPTApplications() {
  try {
    const response = await fetch("/api/v1/custom-gpt-application");
    if (!response.ok) {
      throw new Error("Network response was not ok");
    }
    const gptApplications = await response.json();

    const container = document.querySelector(".row.g-4");
    container.innerHTML = "";

    gptApplications.forEach((application) => {
      const appDiv = document.createElement("div");
      appDiv.className = "col-6 col-md-4 col-xl-3 col-xxl-2";

      const appCard = `
                <a href="/custom-gpt-application/${application.uuid}">
                    <div class="app-card app-card-doc shadow-sm h-100">
                        <div class="app-card-body p-3 has-card-actions">
                            <h4 class="app-doc-title truncate mb-0">${application.gpt_name}</h4>
                            <div class="app-doc-meta">
                                <ul class="list-unstyled mb-0">
                                    <li><span class="text-muted">Description:</span> ${application.gpt_description}</li>
                                </ul>
                            </div>
                        </div>
                    </div>
                </a>
            `;

      appDiv.innerHTML = appCard;
      container.appendChild(appDiv);
    });
  } catch (error) {
    console.error("Failed to fetch GPT applications:", error);
  }
}

fetchGPTApplications();
