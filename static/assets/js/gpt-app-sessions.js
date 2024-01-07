let table = document.getElementById("sessionsTable");
let searchBtn = document.getElementById("searchBtn");
let fullPath = new URL(window.location.href);
let current_offset = 0;
let OFFEST_VAL = 20;
let paginateNav = document.getElementById("app-pagination");

fullPath = `/api/v1${fullPath.pathname}?offset=${current_offset * OFFEST_VAL}`;

function addPaginationUI(data) {
  if (!data.items.length > 0) return;
  let ul = paginateNav.children[0];

  let li = document.createElement("li");
  li.className = "page-item disabled";
  li.id = "previous-button";

  let input = document.createElement("input");
  input.type = "button";
  input.value = "Previous";
  input.className = "page-link";
  input.tabIndex = -1;
  input.setAttribute("aria-disabled", "true");

  li.appendChild(input);

  ul.appendChild(li);
  for (let i = 0; i < 5 && i * OFFEST_VAL < data.total_count; i++) {
    let listItem = document.createElement("li");
    listItem.classList.add("page-item");

    let input = document.createElement("input");
    input.setAttribute("value", i + 1);
    input.setAttribute("type", "button");
    input.setAttribute("aria-disabled", "true");
    input.classList.add("page-link");

    if (i + 1 === 1) {
      input.classList.add("active");
    }

    listItem.appendChild(input);

    ul.appendChild(listItem);
  }
  li = document.createElement("li");
  li.className = "page-item";

  input = document.createElement("input");
  input.type = "button";
  input.value = "Next";
  input.className = "page-link";
  input.setAttribute("aria-disabled", "true");

  li.appendChild(input);

  ul.appendChild(li);
}

(async function () {
  let response;
  try {
    response = await fetch(fullPath);
  } catch (e) {
    console.error(e);
  }
  try {
    let data = await response.json();
    let items = data.items;
    for (let i = 0; i < items.length; i++) {
      let row = `<tr>
                        <td class='cell'>${items[i].email}</td>
                        <td class='cell'>${items[i].name}</td>
                        <td class='cell'>${items[i].created_at}</td>
                       </tr>`;
      table.innerHTML += row;
    }
    addPaginationUI(data);
  } catch (e) {
    console.error(e);
  }
})();

searchBtn.addEventListener("click", async (e) => {
  let name = document.getElementById("searchName").value;
  let email = document.getElementById("searchEmail").value;
  let startDate = document.getElementById("startDate").value;
  let endDate = document.getElementById("endDate").value;

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
