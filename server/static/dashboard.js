
const $ = (id) => document.getElementById(id);
const rubles = new Intl.NumberFormat("ru-RU", {style: "currency", currency: "RUB"});
const operationNames = {receipt: "Приход", shipment: "Расход"};
const pages = {products: "Товары", ...operationNames, purchases: "Закупки", reports: "Отчёты"};
let catalog = [];
let movements = [];
let purchases = [];
let page = "products";
let filter = "all";
let sort = {key: "id", direction: 1};
let pending = null;
let loading = 0;

async function api(path, data) {
    const response = await fetch("/api/" + path, data ? {
        method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data)
    } : {});
    const payload = await response.json().catch(() => null);
    if (!response.ok || payload === null) {
        throw Object.assign(new Error(payload?.error || "Сервер вернул HTTP " + response.status), {status: response.status});
    }
    return payload;
}

function compare(a, b) {
    const left = a[sort.key];
    const right = b[sort.key];
    if (typeof left === "string" || typeof right === "string") {
        return String(left ?? "").localeCompare(String(right ?? ""), "ru") * sort.direction;
    }
    return ((left ?? -1) - (right ?? -1)) * sort.direction;
}

function renderTable(columns, records) {
    const head = document.createElement("tr");
    for (const {key, title, number} of columns) {
        const th = document.createElement("th");
        th.scope = "col";
        if (number) th.className = "n";
        th.setAttribute("aria-sort", sort.key === key ? (sort.direction > 0 ? "ascending" : "descending") : "none");
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = title + (sort.key === key ? (sort.direction > 0 ? " ↑" : " ↓") : "");
        button.onclick = () => {
            sort = {key, direction: sort.key === key ? -sort.direction : 1};
            render();
        };
        th.append(button);
        head.append(th);
    }
    $("columns").replaceChildren(head);
    $("rows").replaceChildren(...records.slice().sort(compare).map((record) => {
        const row = document.createElement("tr");
        for (const col of columns) {
            const cell = row.insertCell();
            cell.textContent = col.format ? col.format(record) : record[col.key];
            if (col.number) cell.classList.add("n");
            if (col.key === "stock" && record.stock < record.minimum) cell.classList.add("low");
        }
        return row;
    }));
}

function render() {
    const search = $("search").value.trim().toLocaleLowerCase("ru");
    const matches = (row) => (row.name + " " + row.barcode).toLocaleLowerCase("ru").includes(search);
    const category = $("category").value;
    let records;
    let columns;
    if (page === "products") {
        records = catalog.filter((row) => matches(row) && (!category || row.category === category)
            && (filter !== "low" || row.stock < row.minimum)
            && (filter !== "available" || row.stock > 0));
        columns = [
            {key:"id", title:"Арт.", format: r => "A-" + (100 + r.id)},
            {key:"name",title:"Название"},
            {key:"category",title:"Категория"},
            {key:"stock",title:"Кол-во",number:true},
            {key:"price_kopecks", title:"Цена, ₽", number:true, format:r => r.price_kopecks == null ? "—" : rubles.format(r.price_kopecks / 100)}
        ];
        if (filter === "low") {
            records = records.map((r) => ({...r, shortage:r.minimum-r.stock}));
            columns.push({key:"shortage",title:"До минимума",number:true});
        }
    } else if (page === "purchases") {
        records = purchases.filter(matches);
        columns = [
            {key:"name",title:"Название"}, {key:"stock",title:"Остаток",number:true},
            {key:"minimum",title:"Минимум",number:true},
            {key:"quantity",title:"К пополнению",number:true,format:r=>r.status==="open" ? r.quantity : "—"},
            {key:"status",title:"Статус",format:r=>r.status==="open" ? "Открыта" : "Закрыта"}
        ];
    } else {
        records = movements.filter((r) => matches(r) && (page === "reports" || r.kind === page));
        columns = [
            {key:"id",title:"№"}, {key:"name",title:"Товар"}, {key:"kind",title:"Операция",format:r=>operationNames[r.kind]},
            {key:"quantity",title:"Кол-во",number:true},{key:"stock_after",title:"Остаток после",number:true},
            {key:"created_at",title:"Дата и время UTC"}
        ];
    }
    renderTable(columns, records);
    $("status").hidden = records.length !== 0;
    $("status").textContent = records.length ? "" : "Ничего не найдено";
    $("rows-info").textContent = page === "products" ? "Записей: " + records.length + " из " + catalog.length : "Записей: " + records.length;
    $("total-value").textContent = "Стоимость склада: " + rubles.format(catalog.reduce((sum,r)=>sum+r.stock*(r.price_kopecks ?? 0),0)/100);
}

async function refresh() {
    const sequence = ++loading;
    try {
        const productsRequest = api("products");
        const secondary = page === "purchases" ? api("purchases") : page === "products" ? null : api("movements");
        const [products, data] = await Promise.all([productsRequest, secondary]);
        if (sequence !== loading) return;
        catalog = products;
        if (page === "purchases") purchases = data;
        else if (data) movements = data;
        const category = $("category").value;
        const categories = [...new Set(catalog.map((row)=>row.category))].sort((a,b)=>a.localeCompare(b,"ru"));
        $("category").replaceChildren(new Option("Все категории",""), ...categories.map((value)=>new Option(value,value)));
        $("category").value = categories.includes(category) ? category : "";
        $("items").textContent = catalog.length;
        $("units").textContent = catalog.reduce((count,row)=>count+row.stock,0);
        $("low").textContent = catalog.filter((row)=>row.stock<row.minimum).length;
        render();
    } catch (error) {
        if (sequence !== loading) return;
        $("status").hidden = false;
        $("status").textContent = error.message;
    }
}

function show(next, stockFilter = "all") {
    page = next;
    filter = stockFilter;
    sort = next === "products"
        ? {key: stockFilter === "available" ? "stock" : stockFilter === "low" ? "shortage" : "id", direction: stockFilter === "all" ? 1 : -1}
        : {key:"id",direction:-1};
    $("title").textContent = pages[page];
    $("category").hidden = page !== "products";
    $("low-filter").hidden = page !== "products";
    $("low-filter").setAttribute("aria-pressed", String(filter === "low"));
    $("add").hidden = page !== "products";
    $("new").hidden = !(page in operationNames) && pending === null;
    $("add-form").hidden = true;
    $("search").value = "";
    $("category").value = "";
    for (const element of document.querySelectorAll("[data-page]")) {
        element.setAttribute("aria-current", element.dataset.page === page ? "page" : "false");
    }
    for (const element of document.querySelectorAll("[data-stock]")) {
        element.setAttribute("aria-pressed", String(page === "products" && element.dataset.stock === filter));
    }
    $("columns").replaceChildren();
    $("rows").replaceChildren();
    $("status").hidden = false;
    $("status").textContent = "Загрузка…";
    refresh();
}

document.querySelectorAll("[data-page]").forEach(button => button.onclick = () => show(button.dataset.page));
document.querySelectorAll("[data-stock]").forEach(button => button.onclick = () => show("products", button.dataset.stock));
$("low-filter").onclick = () => show("products", filter === "low" ? "all" : "low");
$("search").oninput = render;
$("category").onchange = render;
$("scanner").onclick = () => $("scanner-help").showModal();
$("add").onclick = () => {
    $("add-form").hidden = !$("add-form").hidden;
    if (!$("add-form").hidden) $("add-form").elements.barcode.focus();
};
$("add-form").onsubmit = async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    const body = Object.fromEntries(values);
    const button = form.querySelector("button");
    body.price_kopecks = Math.round(Number(body.price) * 100);
    delete body.price;
    for (const key of ["stock","minimum","target"]) body[key] = Number(body[key]);
    button.disabled = true;
    $("add-status").textContent = "Сохранение…";
    try {
        await api("products", body);
        form.reset();
        form.hidden = true;
        $("add-status").textContent = "";
        refresh();
    } catch (error) {
        $("add-status").textContent = error.message;
    } finally {
        button.disabled = false;
    }
};

function lockOperation(posting) {
    $("product").disabled = pending !== null;
    $("quantity").disabled = pending !== null;
    $("close").disabled = posting;
    $("submit").disabled = posting;
    $("submit").textContent = pending ? "Повторить отправку" : "Провести";
}
$("new").onclick = () => {
    $("product").replaceChildren(...catalog.map((r)=>new Option(r.name + " · " + r.stock + " шт.",r.barcode)));
    if (pending) {
        $("product").value = pending.barcode;
        $("quantity").value = pending.quantity;
    }
    $("operation-title").textContent = operationNames[pending?.kind ?? page];
    $("operation-status").textContent = pending ? "Операция ждёт подтверждения сервера." : "";
    lockOperation(false);
    $("dialog").showModal();
};
$("close").onclick = () => $("dialog").close();
$("dialog").addEventListener("cancel",event => { if ($("submit").disabled) event.preventDefault(); });
$("operation").onsubmit = async (event) => {
    event.preventDefault();
    if ($("submit").disabled) return;
    pending ??= {barcode:$("product").value,kind:page,quantity:Number($("quantity").value),
        request_id:Array.from(crypto.getRandomValues(new Uint8Array(16)),n=>n.toString(16).padStart(2,"0")).join("")};
    lockOperation(true);
    $("operation-status").textContent = "Отправка…";
    try {
        await api("movements",pending);
        pending = null;
        $("dialog").close();
        show(page,filter);
    } catch (error) {
        if ([400,404,409,413].includes(error.status)) pending = null;
        $("operation-status").textContent = pending ? "Ответ не получен. Повторите отправку." : error.message;
    } finally {
        lockOperation(false);
    }
};
show("products");

