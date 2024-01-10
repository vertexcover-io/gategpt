let table = document.getElementById("sessionsTable");
let searchBtn = document.getElementById("searchBtn");
let mainDiv = document.getElementById("orders-all");
let tableTitle = document.getElementById("title");
let paginateNav = document.getElementById("app-pagination");

let currentOffset = 0;
let OFFEST_VAL = 20;
let paginateUl = paginateNav.children[0];
let navOffset = 1;
let totalCount;
let previous;
let next;

let fullPath = new URL(window.location.href);
let pathSegments = fullPath.pathname.split("/");

let gptApplicationId = pathSegments[pathSegments.length - 3];

fullPath = `/api/v1${fullPath.pathname}`;

async function increasePagination() {
  while (paginateUl.childNodes.length > 3) {
    paginateUl.removeChild(paginateUl.childNodes[1]);
  }
  for (let i = 0, value = currentOffset + 2; i < 5; i++, value = value + 1) {
    let listItem = document.createElement("li");
    listItem.classList.add("page-item");

    let input = document.createElement("input");
    input.setAttribute("value", value);
    input.setAttribute("type", "button");
    input.classList.add("page-link");
    input.addEventListener("click", (e) => handlePaginationUI(e.target));

    listItem.appendChild(input);
    paginateUl.insertBefore(listItem, next.parentNode);
    if (value * OFFEST_VAL > totalCount) break;
  }
  navOffset = 1;
}

async function decreasePagination() {
  while (paginateUl.childNodes.length > 3) {
    paginateUl.removeChild(paginateUl.childNodes[2]);
  }
  let elemn = paginateUl.childNodes[1];
  for (let i = 0, value = currentOffset - 3; i < 4; i++, value = value + 1) {
    let listItem = document.createElement("li");
    listItem.classList.add("page-item");

    let input = document.createElement("input");
    input.setAttribute("value", value);
    input.setAttribute("type", "button");
    input.classList.add("page-link");
    input.addEventListener("click", (e) => handlePaginationUI(e.target));

    listItem.appendChild(input);
    paginateUl.insertBefore(listItem, elemn);
  }
  navOffset = 5;
}
async function handlePaginationUI(e) {
  paginateUl.childNodes.forEach((li) => {
    let input = li.querySelector("input");
    if (input && !parseInt(input.value)) return;
    li.classList.remove("active");
  });
  if (e.value !== "Previous" || e.target.value !== "Next") {
    e.parentNode.classList.add("active");
  }

  for (let i = 1; i <= 5; i++) {
    let li = paginateUl.children[i];
    if (li.classList.contains("active")) {
      navOffset = i;
      break;
    }
  }
  currentOffset = parseInt(e.value) - 1;
  if (
    currentOffset >= 4 &&
    currentOffset * OFFEST_VAL < totalCount &&
    navOffset == 5
  ) {
    increasePagination();
  }
  if (currentOffset >= 4 && navOffset == 1) {
    decreasePagination();
  }
  await apiSearch();
}

function addPaginationUI(data) {
  if (!data.items.length > 0) return;

  while (paginateUl.childNodes.length) {
    paginateUl.removeChild(paginateUl.childNodes[0]);
  }

  let li = document.createElement("li");
  li.className = "page-item";
  if (currentOffset == 0) {
    li.classList.add("disabled");
  }
  li.id = "previous-button";

  let input = document.createElement("input");
  input.type = "button";
  input.value = "Previous";
  input.className = "page-link";
  input.tabIndex = -1;
  input.setAttribute("disabled", "true");
  previous = input;

  li.appendChild(input);

  paginateUl.appendChild(li);
  for (let i = 0; i < 5 && i * OFFEST_VAL < data.total_count; i++) {
    if (i * 20 > totalCount) break;
    let listItem = document.createElement("li");
    listItem.classList.add("page-item");

    let input = document.createElement("input");
    input.setAttribute("value", i + 1);
    input.setAttribute("type", "button");
    input.classList.add("page-link");

    if (i == navOffset - 1) {
      listItem.classList.add("active");
    }

    listItem.appendChild(input);

    paginateUl.appendChild(listItem);
  }
  li = document.createElement("li");
  li.className = "page-item";

  input = document.createElement("input");
  input.type = "button";
  input.value = "Next";
  input.className = "page-link";

  console.log(paginateUl.children.length, currentOffset * 20);
  if (currentOffset * OFFEST_VAL > totalCount) {
    li.classList.add("disabled");
    input.setAttribute("disabled", "true");
  }

  next = input;

  li.appendChild(input);

  paginateUl.appendChild(li);
  paginateUl.childNodes.forEach((element) => {
    element.addEventListener("click", async (e) => {
      let toClick;
      if (e.target.children.length) {
        if (e.target.children[0].getAttribute("disabled") === "true") {
          return;
        }
      }
      if (e.target.value === "Next") {
        if (navOffset < paginateUl.children.length - 2) {
          ++navOffset;
        }
        toClick = paginateUl.children[navOffset].children[0];
      } else if (e.target.value == "Previous") {
        if (navOffset !== 1) {
          --navOffset;
        }
        toClick = paginateUl.children[navOffset].children[0];
      } else {
        toClick = e.target;
      }
      handlePaginationUI(toClick);
    });
  });
}

function getQueryParams() {
  let nameEmail = document.getElementById("searchNameEmail").value;
  let startDate = document.getElementById("startDate").value;
  let endDate = document.getElementById("endDate").value;

  let queryParams = new URLSearchParams();
  if (nameEmail) {
    queryParams.append("name", nameEmail);
    queryParams.append("email", nameEmail);
  }
  if (startDate) {
    startDate = new Date(startDate).toISOString();
    queryParams.append("start_datetime", startDate);
  }
  if (endDate) {
    endDate = new Date(endDate).toISOString();
    queryParams.append("end_datetime", endDate);
  }
  if (currentOffset) {
    queryParams.append("offset", currentOffset * 20);
  }
  return queryParams;
}
async function apiSearch() {
  let queryParams = getQueryParams();

  let pathname = new URL(window.location.href).pathname;
  let fullPath = `/api/v1${pathname}?${queryParams.toString()}`;

  try {
    let response = await fetch(fullPath);
    if (!response.ok) {
      console.log("not ok response", response.status);
    }
    if (response.status === 404) {
      window.location.href = "/404";
      return;
    }
    let data = await response.json();
    let items = data.items;
    totalCount = items.total_count;

    let tableBody = table.getElementsByTagName("tbody");
    let tableRows = table.getElementsByTagName("tr");
    for (let i = tableRows.length - 1; i > 0; i--) {
      table.removeChild(tableBody[i]);
    }
    if (!items.length) {
      let h2 = document.createElement("h2");
      h2.className = "text-center";
      h2.textContent = "No sessions found :(";
      mainDiv.appendChild(h2);
    }

    items.forEach((session) => {
      let createdAt = moment(session.created_at);
      let createdAtFormatted = createdAt.format("YYYY-MM-DD HH:mm:ss");

      let row = `<tr>
                        <td class = 'cell'>${session.email}</td>
                        <td class = 'cell'>${session.name}</td>
                        <td class = 'cell' data-toggle = "tooltip" data-placement = "top" title = "${createdAtFormatted}">${createdAt.fromNow()}</td>
                       </tr>`;
      table.innerHTML += row;
    });
    addPaginationUI(data);
  } catch (error) {
    console.error("Error:", error);
  }
}

searchBtn.addEventListener("click", async (e) => {
  e.preventDefault();
  await apiSearch();
});

async function getGptApplication() {
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
  tableTitle.textContent = `${data.gpt_name}'s Sessions`;
}

async function main() {
  getGptApplication();
  apiSearch();
}

main();
