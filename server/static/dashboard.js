
const $ = (id) => document.getElementById(id);
const views = {
  products: ["Товары", "Следите за остатками и проводите складские операции.", "Каталог товаров", ["Товар", "Штрихкод", "Остаток", "Минимум", "Состояние"]],
  movements: ["Журнал", "Хронология приёмок и отгрузок.", "История операций", ["Товар", "Операция", "Количество", "Остаток после", "Время (UTC)"]],
  purchases: ["Закупки", "Расчётные заявки на пополнение запасов.", "Заявки на закупку", ["Товар", "Статус", "К пополнению", "Текущий остаток"]]
};
let page = "products";
let products = [];
let entries = [];
let requestNumber = 0;
let pending = null;
let posting = false;

async function api(path, data) {
  const response = await fetch("/api/" + path, data ? {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data)
  } : {});
  const body = await response.json().catch(() => null);
  if (!response.ok || body === null) {
    throw Object.assign(new Error(body?.error || "Ответ сервера: " + response.status), {status: response.status});
  }
  return body;
}

function pill(text, warning = false) {
  const span = document.createElement("span");
  span.className = warning ? "pill warn" : "pill";
  span.textContent = text;
  return span;
}

function render() {
  const query = $("search").value.trim().toLocaleLowerCase("ru");
  const filtered = entries.filter((row) => (row.name + " " + row.barcode).toLocaleLowerCase("ru").includes(query));
  $("rows").replaceChildren(...filtered.map((row) => {
    const tr = document.createElement("tr");
    const values = page === "products"
      ? [row.name, row.barcode, row.stock + " шт.", row.minimum + " шт.", row.stock < row.minimum ? pill("Ниже минимума", true) : pill("В норме")]
      : page === "movements"
        ? [row.name, row.kind === "receipt" ? pill("Приёмка") : pill("Отгрузка", true), row.quantity + " шт.", row.stock_after + " шт.", row.created_at]
        : [row.name, row.status === "open" ? pill("Открыта", true) : pill("Закрыта"), row.status === "open" ? row.quantity + " шт." : "—", row.stock + " шт."];
    for (const value of values) {
      const td = tr.insertCell();
      if (value instanceof Node) td.append(value);
      else td.textContent = value;
    }
    return tr;
  }));
  $("status").textContent = filtered.length ? "" : query ? "Совпадений нет." : "Записей пока нет.";
  $("status").hidden = filtered.length > 0;
}

async function load() {
  const requestedPage = page;
  const current = ++requestNumber;
  $("status").hidden = false;
  $("status").textContent = "Загрузка…";
  try {
    const [catalog, data] = await Promise.all([api("products"), requestedPage === "products" ? null : api(requestedPage)]);
    if (current !== requestNumber) return;
    products = catalog;
    entries = data ?? catalog;
    $("items").textContent = products.length;
    $("units").textContent = products.reduce((sum, row) => sum + row.stock, 0);
    $("low").textContent = products.filter((row) => row.stock < row.minimum).length;
    render();
  } catch (error) {
    if (current !== requestNumber) return;
    $("status").textContent = "Не удалось загрузить данные. Нажмите «Обновить».";
  }
}

function openPage(next) {
  page = next;
  const [title, description, list, columns] = views[page];
  $("title").textContent = title;
  $("description").textContent = description;
  $("list-title").textContent = list;
  for (const button of document.querySelectorAll("nav button")) {
    button.classList.toggle("active", button.dataset.page === page);
    button.setAttribute("aria-pressed", String(button.dataset.page === page));
  }
  const row = document.createElement("tr");
  for (const label of columns) {
    const th = document.createElement("th");
    th.scope = "col";
    th.textContent = label;
    row.append(th);
  }
  $("columns").replaceChildren(row);
  $("search").value = "";
  entries = [];
  $("rows").replaceChildren();
  load();
}

function lockForm() {
  for (const id of ["product", "kind", "quantity"]) $(id).disabled = pending !== null;
  $("submit").disabled = posting;
  $("close").disabled = posting;
}

document.querySelectorAll("nav button").forEach((button) => button.onclick = () => openPage(button.dataset.page));
$("search").oninput = render;
$("refresh").onclick = load;
$("new").onclick = () => {
  $("product").replaceChildren(...products.map((row) => new Option(row.name + " · " + row.stock + " шт.", row.barcode)));
  if (pending) {
    $("product").value = pending.barcode;
    $("kind").value = pending.kind;
    $("quantity").value = pending.quantity;
  }
  $("submit").textContent = pending ? "Повторить отправку" : "Провести операцию";
  $("operation-status").textContent = pending ? "Операция ждёт подтверждения сервера." : "";
  lockForm();
  $("dialog").showModal();
};
$("close").onclick = () => $("dialog").close();
$("dialog").addEventListener("cancel", (event) => { if (posting) event.preventDefault(); });
$("operation").onsubmit = async (event) => {
  event.preventDefault();
  if (posting) return;
  pending ??= { barcode: $("product").value, kind: $("kind").value, quantity: Number($("quantity").value), request_id: crypto.randomUUID() };
  posting = true;
  lockForm();
  $("operation-status").textContent = "Отправка…";
  try {
    await api("movements", pending);
    pending = null;
    $("dialog").close();
    openPage(page);
  } catch (error) {
    if ([400, 404, 409, 413].includes(error.status)) pending = null;
    $("operation-status").textContent = pending ? "Подтверждение не получено. Повторите отправку." : error.message;
    $("submit").textContent = pending ? "Повторить отправку" : "Провести операцию";
  } finally {
    posting = false;
    lockForm();
  }
};
openPage("products");
