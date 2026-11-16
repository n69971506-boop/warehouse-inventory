
package ru.study.warehouse

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.RippleDrawable
import android.content.res.ColorStateList
import android.os.Bundle
import android.text.InputType
import android.view.View
import android.view.Gravity
import android.widget.*
import android.net.Uri
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.text.NumberFormat
import java.util.Locale
import java.util.UUID
import java.util.concurrent.Executors

class MainActivity : ComponentActivity() {
    private val ink = Color.parseColor("#222622")
    private val green = Color.parseColor("#2F4A3A")
    private val paper = Color.parseColor("#F5F2EA")
    private val muted = Color.parseColor("#55584F")
    private val soft = Color.parseColor("#ECE8DC")
    private val white = Color.parseColor("#FFFDF8")
    private val line = Color.parseColor("#DCD7C9")
    private val money = NumberFormat.getCurrencyInstance(Locale.forLanguageTag("ru-RU"))
    private val network = Executors.newSingleThreadExecutor()
    private val preferences by lazy { getSharedPreferences("warehouse", MODE_PRIVATE) }
    private lateinit var content: LinearLayout
    private lateinit var notice: TextView
    private lateinit var barcode: EditText
    private lateinit var quantity: EditText
    private lateinit var kind: Spinner
    private var busy = false
    private var screen = "Операция"
    private var pending: String?
        get() = preferences.getString("pending", null)
        set(value) { preferences.edit().putString("pending", value).commit() }
    private val server get() = preferences.getString("server", "http://10.0.2.2:8000")!!
    private val barcodePattern = Regex("[0-9]{8,14}")
    private val cameraPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) openScanner()
        else feedback("Камера недоступна. Введите код вручную или разрешите доступ в настройках.", true)
    }
    private val scanner = registerForActivityResult(ScanContract()) { result ->
        val code = result.contents?.trim()
        if (code != null && pending == null && screen == "Операция") {
            barcode.setText(code)
            lookupBarcode(scanned = true)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (savedInstanceState == null) {
            window.statusBarColor = Color.parseColor("#1E1B6B")
            window.navigationBarColor = Color.parseColor("#06B6D4")
            val splash = WarehouseSplash(this)
            setContentView(splash)
            splash.postDelayed({ if (!isFinishing && !isDestroyed) show("Операция") }, 1150)
        } else {
            show("Операция")
        }
        if (savedInstanceState != null && pending == null) {
            barcode.setText(savedInstanceState.getString("barcode", ""))
            quantity.setText(savedInstanceState.getString("quantity", "1"))
            kind.setSelection(savedInstanceState.getInt("kind", 0))
        }
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        if (screen == "Операция" && ::barcode.isInitialized) {
            outState.putString("barcode", barcode.text.toString())
            outState.putString("quantity", quantity.text.toString())
            outState.putInt("kind", kind.selectedItemPosition)
        }
    }

    private fun dp(value: Int) = (resources.displayMetrics.density * value).toInt()

    private fun panel(color: Int, radius: Int = 4) = GradientDrawable().apply {
        setColor(color)
        cornerRadius = dp(radius).toFloat()
        if (color == white || color == soft) setStroke(dp(1), line)
    }

    private fun pressable(color: Int, radius: Int) = RippleDrawable(
        ColorStateList.valueOf(Color.parseColor("#302F4A3A")), panel(color, radius), null
    )

    private fun feedback(message: String, warning: Boolean = false) {
        notice.visibility = if (message.isEmpty()) View.GONE else View.VISIBLE
        notice.text = message
        notice.setTextColor(if (warning) Color.parseColor("#A8432C") else green)
        notice.background = panel(if (warning) Color.parseColor("#F1E8D4") else soft)
    }

    private fun label(text: String, size: Float = 16f): TextView = TextView(this).apply {
        this.text = text
        textSize = size
        setTextColor(ink)
        if (size >= 19f) typeface = Typeface.create("serif", Typeface.BOLD)
        setPadding(0, dp(8), 0, dp(8))
        content.addView(this)
    }

    private fun input(hintText: String, initial: String, type: Int) = EditText(this).apply {
        hint = hintText
        inputType = type
        setSingleLine()
        setText(initial)
        background = panel(white)
        setTextColor(ink)
        setHintTextColor(muted)
        textSize = 16f
        minimumHeight = dp(50)
        setPadding(dp(14), dp(12), dp(14), dp(12))
        content.addView(this)
    }

    private fun button(title: String, action: () -> Unit) = Button(this).apply {
        text = title
        isAllCaps = false
        val primary = title.startsWith("Провести") || title.startsWith("Повторить") || title.startsWith("Сканировать")
        setTextColor(if (primary) Color.WHITE else green)
        background = pressable(if (primary) green else soft, 4)
        setTypeface(typeface, Typeface.BOLD)
        minimumHeight = dp(48)
        setOnClickListener { if (!busy) action() }
        content.addView(this, LinearLayout.LayoutParams(-1, dp(48)).apply {
            topMargin = dp(8)
        })
    }

    private fun show(page: String) {
        screen = page
        content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(18), dp(20), dp(22))
        }
        setContentView(ScrollView(this).apply {
            setBackgroundColor(paper)
            addView(content)
        })
        window.statusBarColor = green
        window.navigationBarColor = green
        val banner = LinearLayout(this).apply {
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(10), 0, dp(10), 0)
            background = panel(green)
            addView(ImageView(context).apply {
                setImageResource(R.drawable.warehouse_icon)
            }, LinearLayout.LayoutParams(dp(35), dp(35)))
            addView(TextView(context).apply {
                text = "Склад — учёт товаров"
                textSize = 18f
                typeface = Typeface.create("serif", Typeface.BOLD)
                setTextColor(Color.parseColor("#F1EAD8"))
                setPadding(dp(9), 0, 0, 0)
            })
        }
        content.addView(banner, LinearLayout.LayoutParams(-1, dp(54)).apply { bottomMargin = dp(8) })
        val navigation = LinearLayout(this)
        content.addView(navigation)
        for ((title, icon) in listOf("Операция" to "Учёт", "Каталог" to "Товары",
            "Журнал" to "Журнал", "Закупки" to "Закупки")) {
            navigation.addView(Button(this).apply {
                text = icon
                isAllCaps = false
                isEnabled = page != title
                textSize = 13f
                setTextColor(if (page == title) Color.WHITE else green)
                background = pressable(if (page == title) green else soft, 4)
                setTypeface(typeface, Typeface.BOLD)
                setPadding(0, 0, 0, 0)
                setOnClickListener { if (!busy) show(title) }
            }, LinearLayout.LayoutParams(0, dp(48), 1f).apply { marginEnd = dp(4) })
        }
        label(page, 22f)
        notice = label("", 14f).apply {
            setPadding(dp(13), dp(10), dp(13), dp(10))
            accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
        }
        feedback("")
        if (page == "Операция") {
            operation()
            return
        }
        val endpoint = when (page) {
            "Каталог" -> "/api/products"
            "Журнал" -> "/api/movements"
            else -> "/api/purchases"
        }
        button("Обновить") { show(page) }
        fetch(endpoint) { _, body ->
            val rows = JSONArray(body)
            feedback(if (rows.length() == 0) "Список пуст" else "")
            for (index in 0 until rows.length()) {
                val row = rows.getJSONObject(index)
                val name = row.getString("name")
                val description = when (page) {
                    "Каталог" -> {
                        val stock = row.getInt("stock")
                        val minimum = row.getInt("minimum")
                        val status = if (stock < minimum) "Ниже минимума" else "В норме"
                        val category = row.optString("category", "Без категории")
                        val price = if (row.isNull("price_kopecks")) "" else " · ${money.format(row.getLong("price_kopecks") / 100.0)}"
                        "$category$price\n${row.getString("barcode")}\nОстаток $stock шт. · Минимум $minimum\n$status"
                    }
                    "Журнал" -> {
                        val operation = if (row.getString("kind") == "receipt") "Приёмка" else "Отгрузка"
                        "$operation ${row.getInt("quantity")} шт. · Остаток ${row.getInt("stock_after")}\n${row.getString("created_at")} UTC"
                    }
                    else -> {
                        val state = if (row.getString("status") == "open") "Открыта" else "Закрыта"
                        "$state · ${row.getInt("quantity")} шт. к пополнению\nОстаток ${row.getInt("stock")} шт."
                    }
                }
                val card = LinearLayout(this).apply {
                    orientation = LinearLayout.VERTICAL
                    background = panel(white)
                    setPadding(dp(16), dp(13), dp(16), dp(13))
                    addView(TextView(context).apply {
                        text = name
                        textSize = 17f
                        setTextColor(ink)
                        setTypeface(typeface, Typeface.BOLD)
                    })
                    addView(TextView(context).apply {
                        text = description
                        textSize = 14f
                        setTextColor(muted)
                        setLineSpacing(dp(3).toFloat(), 1f)
                        setPadding(0, dp(5), 0, 0)
                    })
                    if (page == "Каталог") setOnClickListener {
                        show("Операция")
                        if (pending == null) barcode.setText(row.getString("barcode"))
                    }
                }
                content.addView(card, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(9) })
            }
        }
    }

    private fun operation() {
        val saved = pending?.let(::JSONObject)
        label("Штрихкод")
        barcode = input("8–14 цифр", saved?.optString("barcode") ?: "", InputType.TYPE_CLASS_NUMBER)
        button("Сканировать камерой") { startScanner() }.isEnabled = saved == null
        button("Найти товар") { lookupBarcode() }
        label("Вид операции")
        kind = Spinner(this).apply {
            adapter = ArrayAdapter(this@MainActivity, android.R.layout.simple_spinner_dropdown_item,
                listOf("Приёмка", "Отгрузка"))
            setSelection(if (saved?.optString("kind") == "shipment") 1 else 0)
        }
        content.addView(kind)
        label("Количество в штуках")
        quantity = input("Количество", saved?.optString("quantity") ?: "1", InputType.TYPE_CLASS_NUMBER)
        setFormEnabled(saved == null)
        if (saved != null) feedback("Есть операция без подтверждения. Повторите отправку.", true)
        button(if (saved == null) "Провести операцию" else "Повторить отправку") { submit() }
        label("Подключение", 19f)
        val address = input("Адрес API", server, InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI)
        button("Сохранить адрес") {
            val value = address.text.toString().trim().trimEnd('/')
            val parsed = runCatching { URL(value) }.getOrNull()
            if (pending != null) feedback("Сначала получите подтверждение операции.")
            else if (parsed == null || parsed.protocol !in listOf("http", "https") ||
                parsed.host.isBlank() || parsed.path.isNotEmpty() || parsed.query != null ||
                parsed.ref != null || parsed.userInfo != null) {
                feedback("Укажите адрес вида http://192.168.1.10:8000")
            } else {
                preferences.edit().putString("server", value).apply()
                feedback("Адрес сохранён")
            }
        }
        button("Разрешение камеры") {
            startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.fromParts("package", packageName, null)))
        }
    }

    private fun startScanner() {
        if (pending != null) return
        if (!packageManager.hasSystemFeature(PackageManager.FEATURE_CAMERA_ANY)) {
            feedback("На этом устройстве нет доступной камеры. Введите штрихкод вручную.", true)
        } else if (checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            cameraPermission.launch(Manifest.permission.CAMERA)
        } else {
            openScanner()
        }
    }

    private fun openScanner() {
        scanner.launch(ScanOptions()
            .setCaptureActivity(WarehouseCaptureActivity::class.java)
            .setOrientationLocked(false)
            .setDesiredBarcodeFormats(ScanOptions.ONE_D_CODE_TYPES + ScanOptions.QR_CODE)
            .setPrompt("Поместите штрихкод целиком в рамку")
            .setBeepEnabled(false))
    }

    private fun lookupBarcode(scanned: Boolean = false) {
        val code = barcode.text.toString().trim()
        if (!code.matches(barcodePattern)) {
            feedback(if (scanned) "Код считан, но для товара нужно от 8 до 14 цифр."
                else "Введите штрихкод из 8–14 цифр", true)
            return
        }
        fetch("/api/products/$code", scannedCode = code.takeIf { scanned }) { _, body ->
            val item = JSONObject(body)
            feedback("${item.getString("name")} · остаток ${item.getInt("stock")} шт.")
        }
    }

    private fun setFormEnabled(enabled: Boolean) {
        barcode.isEnabled = enabled
        quantity.isEnabled = enabled
        kind.isEnabled = enabled
    }

    private fun submit() {
        val code = barcode.text.toString().trim()
        val qty = quantity.text.toString().toIntOrNull()
        if (qty == null || qty !in 1..1_000_000 || !code.matches(barcodePattern)) {
            feedback("Проверьте штрихкод и количество от 1 до 1 000 000")
            return
        }
        val payload = pending ?: JSONObject()
            .put("barcode", code)
            .put("quantity", qty)
            .put("kind", if (kind.selectedItemPosition == 0) "receipt" else "shipment")
            .put("request_id", UUID.randomUUID().toString()).toString()
        pending = payload
        setFormEnabled(false)
        fetch("/api/movements", payload) { status, body ->
            if (status in 200..299) {
                val movement = JSONObject(body)
                pending = null
                show("Операция")
                feedback("Операция №${movement.getInt("id")} проведена. Остаток ${movement.getInt("stock_after")} шт.")
            }
        }
    }

    private fun fetch(path: String, json: String? = null, scannedCode: String? = null, onSuccess: (Int, String) -> Unit) {
        busy = true
        feedback("Запрос к серверу…")
        val url = server + path
        network.execute {
            val result = runCatching {
                val connection = URL(url).openConnection() as HttpURLConnection
                try {
                    connection.connectTimeout = 5000
                    connection.readTimeout = 5000
                    if (json != null) {
                        connection.requestMethod = "POST"
                        connection.doOutput = true
                        connection.setRequestProperty("Content-Type", "application/json")
                        connection.outputStream.use { it.write(json.toByteArray(Charsets.UTF_8)) }
                    }
                    val status = connection.responseCode
                    val stream = if (status in 200..299) connection.inputStream else connection.errorStream
                    status to (stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() } ?: "")
                } finally {
                    connection.disconnect()
                }
            }
            runOnUiThread {
                if (isDestroyed) return@runOnUiThread
                busy = false
                result.fold({ (status, body) ->
                    if (status in 200..299) {
                        runCatching { onSuccess(status, body) }.onFailure {
                            feedback("Сервер прислал ответ в неверном формате")
                        }
                    } else {
                        val message = runCatching { JSONObject(body).getString("error") }
                            .getOrDefault("Ответ сервера HTTP $status")
                        if (json != null && status in listOf(400, 404, 409, 413)) {
                            pending = null
                            show("Операция")
                            barcode.setText(JSONObject(json).getString("barcode"))
                            quantity.setText(JSONObject(json).getString("quantity"))
                            kind.setSelection(if (JSONObject(json).getString("kind") == "shipment") 1 else 0)
                        }
                        feedback(if (scannedCode == null) message else "Код считан: $scannedCode. $message.", true)
                    }
                }, {
                    feedback(when {
                        scannedCode != null -> "Код считан: $scannedCode. Сервер недоступен. Проверьте адрес в разделе «Подключение»."
                        json == null -> "Нет ответа. Проверьте адрес API и сеть."
                        else -> "Нет подтверждения. Повторите отправку той же операции."
                    }, true)
                })
            }
        }
    }

    override fun onDestroy() {
        network.shutdown()
        super.onDestroy()
    }
}

