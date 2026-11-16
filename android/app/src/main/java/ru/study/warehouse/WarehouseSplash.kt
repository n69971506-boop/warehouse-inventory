
package ru.study.warehouse

import android.animation.ValueAnimator
import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Shader
import android.graphics.Typeface
import android.view.Gravity
import android.view.View
import android.view.animation.DecelerateInterpolator
import android.view.animation.OvershootInterpolator
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView

class WarehouseSplash(context: Context) : FrameLayout(context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()
    private val logo = ImageView(context).apply {
        setImageResource(R.drawable.warehouse_icon)
        contentDescription = null
    }
    private val progress = ProgressBar(context, null, android.R.attr.progressBarStyleHorizontal).apply {
        max = 100
        progressTintList = ColorStateList.valueOf(Color.WHITE)
        progressBackgroundTintList = ColorStateList.valueOf(0x40FFFFFF)
    }
    private val animation = ValueAnimator.ofInt(0, 100).apply {
        duration = 1100
        interpolator = DecelerateInterpolator()
        addUpdateListener { progress.progress = it.animatedValue as Int }
    }

    init {
        setWillNotDraw(false)
        val column = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
        }
        column.addView(logo, LinearLayout.LayoutParams(dp(110), dp(110)))
        column.addView(text("Warehouse", 26f, true), LayoutParams(-2, -2).withTop(22))
        column.addView(text("Учёт товаров на складе", 13f), LayoutParams(-2, -2).withTop(4))
        column.addView(progress, LayoutParams(dp(180), dp(12)).withTop(40))
        column.addView(text("Загрузка данных…", 12f), LayoutParams(-2, -2).withTop(8))
        addView(column, LayoutParams(-1, -2, Gravity.CENTER))
        logo.alpha = 0f
        logo.scaleX = .3f
        logo.scaleY = .3f
        logo.rotation = -20f
        logo.animate().alpha(1f).scaleX(1f).scaleY(1f).rotation(0f)
            .setInterpolator(OvershootInterpolator()).setDuration(650).start()
        animation.start()
    }

    private fun LayoutParams.withTop(top: Int) =
        LinearLayout.LayoutParams(width, height).apply { topMargin = dp(top) }

    private fun text(value: String, size: Float, bold: Boolean = false) = TextView(context).apply {
        text = value
        textSize = size
        setTextColor(if (bold) Color.WHITE else 0xDDFFFFFF.toInt())
        if (bold) setTypeface(typeface, Typeface.BOLD)
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        super.onSizeChanged(w, h, oldw, oldh)
        paint.shader = LinearGradient(0f, 0f, w * .55f, h.toFloat(),
            intArrayOf(Color.parseColor("#1E1B6B"), Color.parseColor("#4F46E5"), Color.parseColor("#06B6D4")),
            floatArrayOf(0f, .55f, 1f), Shader.TileMode.CLAMP)
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        canvas.drawRect(0f, 0f, width.toFloat(), height.toFloat(), paint)
        val overlay = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0x14FFFFFF }
        canvas.drawCircle(width - dp(40).toFloat(), dp(40).toFloat(), dp(130).toFloat(), overlay)
        canvas.drawCircle(dp(40).toFloat(), height - dp(30).toFloat(), dp(100).toFloat(), overlay)
    }

    override fun onDetachedFromWindow() {
        animation.cancel()
        super.onDetachedFromWindow()
    }
}
