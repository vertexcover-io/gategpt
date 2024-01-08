let table = document.getElementById("sessionsTable");
let searchBtn = document.getElementById("searchBtn");
let fullPath = new URL(window.location.href);
let currentOffset = 0;
let OFFEST_VAL = 20;
let paginateNav = document.getElementById("app-pagination");
let paginateUl = paginateNav.children[0];
let navOffset;
let total_count;
let previous;
let next;

table.removeAttribute;

fullPath = `/api/v1${fullPath.pathname}?offset=${currentOffset * OFFEST_VAL}`;

function addClass(n, className) {
  if (n.classList.contains(className)) return;
  n.classList.add(className);
}

function addAttr(n, attrName, value) {
  if (n.hasAttribute(attrName)) return;
  n.setAttribute(attrName, value);
}
function removeClass(n, className) {
  if (!n.classList.contains(className)) return;
  console.log("removing class");
  n.classList.remove(className);
}

function removeAttr(n, attrName) {
  if (!n.hasAttribute(attrName)) return;
  n.removeAttribute(attrName);
}

async function updatePagination() {}

async function handlePaginationUI(e) {
  paginateUl.childNodes.forEach((li) => {
    let input = li.querySelector("input");
    if (input && !parseInt(input.value)) return;
    li.classList.remove("active");
  });
  if (e.value !== "Previous" || e.target.value !== "Next") {
    e.parentNode.classList.add("active");
  }
  if (navOffset === 1) {
    addClass(previous.parentNode, "disabled");
    addAttr(previous, "disabled", "true");
  } else {
    removeClass(previous.parentNode, "disabled");
    removeAttr(previous, "disabled");
  }
  if (currentOffset * 20 > total_count) {
    addClass(next.parentNode, "disabled");
    addAttr(next, "disabled", "true");
  } else {
    removeClass(next.parentNode, "disabled");
    removeAttr(next, "disabled");
  }
  currentOffset = parseInt(e.value) - 1;
  console.log(currentOffset);
  if (currentOffset >= 4 && currentOffset * 20 < total_count) {
    console.log("update avialable");
  }
}

function addPaginationUI(data) {
  if (!data.items.length > 0) return;

  let li = document.createElement("li");
  li.className = "page-item disabled";
  li.id = "previous-button";

  let input = document.createElement("input");
  input.type = "button";
  input.value = "Previous";
  input.className = "page-link";
  input.tabIndex = -1;
  input.setAttribute("disabled", "true");
  navOffset = 1;
  previous = input;

  li.appendChild(input);

  paginateUl.appendChild(li);
  for (let i = 0; i < 5 && i * OFFEST_VAL < data.total_count; i++) {
    let listItem = document.createElement("li");
    listItem.classList.add("page-item");

    let input = document.createElement("input");
    input.setAttribute("value", i + 1);
    input.setAttribute("type", "button");
    input.classList.add("page-link");

    if (i + 1 === 1) {
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
  // input.setAttribute("disabled", "true");
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
        navOffset = parseInt(e.target.value);
        toClick = e.target;
      }
      handlePaginationUI(toClick);
    });
  });
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
    total_count = data.total_count;
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

async function apiSearch() {
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
}

searchBtn.addEventListener("click", async (e) => {
  await apiSearch();
});