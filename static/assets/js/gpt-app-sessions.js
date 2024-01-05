let table = document.getElementById("sessionsTable");
let searchBtn = document.getElementById("searchBtn");
let fullPath = new URL(window.location.href);
fullPath = `/api/v1${fullPath.pathname}`;
(async function () {
  let response;
  try {
    response = await fetch(fullPath);
  } catch (e) {
    console.error(e);
  }
  try {
    let data = await response.json();
    for (let i = 0; i < data.length; i++) {
      let row = `<tr>
                        <td>${data[i].email}</td>
                        <td>${data[i].name}</td>
                        <td>${data[i].created_at}</td>
                       </tr>`;
      table.innerHTML += row;
    }
  } catch (e) {
    console.error(e);
  }
})();

searchBtn.addEventListener("click", async (e) => {
  let name = document.getElementById("searchName").value;
  let email = document.getElementById("searchEmail").value;
  let startDate = document.getElementById("startDate").value;
  let endDate = document.getElementById("endDate").value;
  let limit = document.getElementById("limit").value;
  let offset = document.getElementById("offset").value;

  let queryParams = new URLSearchParams();
  if (name) {
    queryParams.append("name", name);
  }
  if (email) {
    queryParams.append("email", email);
  }
  if (startDate) {
    startDate = new Date(startDate).toISOString();
    queryParams.append("start_date", startDate);
  }
  if (endDate) {
    endDate = new Date(endDate).toISOString();
    queryParams.append("end_date", endDate);
  }
  if (limit) {
    queryParams.append("limit", limit);
  }
  if (offset) {
    queryParams.append("offset", offset);
  }

  let pathname = new URL(window.location.href).pathname;
  let fullPath = `/api/v1${pathname}?${queryParams.toString()}`;

  try {
    let response = await fetch(fullPath);
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    let data = await response.json();

    let tableBody = table.getElementsByTagName("tbody");
    let tableRows = table.getElementsByTagName("tr");
    for (let i = tableRows.length - 1; i > 0; i--) {
      table.removeChild(tableBody[i]);
    }

    data.forEach((session) => {
      let row = `<tr>
                        <td>${session.email}</td>
                        <td>${session.name}</td>
                        <td>${session.created_at}</td>
                       </tr>`;
      table.innerHTML += row;
    });
  } catch (error) {
    console.error("Error:", error);
  }
});
