package com.zeeriz.fleetai.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.zeeriz.fleetai.utils.Format

private const val AXIS_LABEL_SPACE_DP = 46

/** Lightweight line chart (no chart library): area fill, three gridlines, first/middle/last x labels. */
@Composable
fun LineChart(
    values: List<Double>,
    labels: List<String>,
    modifier: Modifier = Modifier,
    color: Color = MaterialTheme.colorScheme.primary,
    height: Dp = 170.dp,
    format: (Double) -> String = { Format.decimal(it, 1) },
) {
    if (values.size < 2 || labels.size != values.size) return
    val measurer = rememberTextMeasurer()
    val labelStyle = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant)
    val gridColor = MaterialTheme.colorScheme.outlineVariant
    Canvas(modifier.fillMaxWidth().height(height)) {
        val left = AXIS_LABEL_SPACE_DP.dp.toPx()
        val top = 8.dp.toPx()
        val bottom = 22.dp.toPx()
        val w = size.width - left
        val h = size.height - top - bottom
        val min = values.min()
        val max = values.max()
        val span = (max - min).takeIf { it > 0 } ?: (if (max == 0.0) 1.0 else max * 0.1)
        val lo = min - span * 0.15
        val hi = max + span * 0.15
        fun x(i: Int) = left + w * i / (values.size - 1)
        fun y(v: Double) = top + (h * (1 - (v - lo) / (hi - lo))).toFloat()

        listOf(lo, (lo + hi) / 2, hi).forEach { v ->
            drawLine(gridColor, Offset(left, y(v)), Offset(size.width, y(v)), strokeWidth = 1.dp.toPx())
            val text = measurer.measure(format(v), labelStyle)
            drawText(text, topLeft = Offset(0f, (y(v) - text.size.height / 2f).coerceIn(0f, size.height - text.size.height)))
        }
        val line = Path().apply {
            values.forEachIndexed { i, v -> if (i == 0) moveTo(x(i), y(v)) else lineTo(x(i), y(v)) }
        }
        val area = Path().apply {
            addPath(line)
            lineTo(x(values.lastIndex), top + h)
            lineTo(x(0), top + h)
            close()
        }
        drawPath(area, Brush.verticalGradient(listOf(color.copy(alpha = 0.22f), color.copy(alpha = 0f)), startY = top, endY = top + h))
        drawPath(line, color, style = Stroke(width = 2.5.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
        drawCircle(color, radius = 4.dp.toPx(), center = Offset(x(values.lastIndex), y(values.last())))

        listOf(0, values.lastIndex / 2, values.lastIndex).distinct().forEach { i ->
            val text = measurer.measure(labels[i], labelStyle)
            val px = (x(i) - text.size.width / 2f).coerceIn(left, size.width - text.size.width)
            drawText(text, topLeft = Offset(px, size.height - text.size.height))
        }
    }
}

/** Vertical bar chart; the last bar is highlighted (current period). */
@Composable
fun BarChart(
    values: List<Double>,
    labels: List<String>,
    modifier: Modifier = Modifier,
    color: Color = MaterialTheme.colorScheme.primary,
    height: Dp = 160.dp,
    format: (Double) -> String = { Format.rupeesShort(it) },
) {
    if (values.isEmpty() || labels.size != values.size) return
    val measurer = rememberTextMeasurer()
    val labelStyle = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant)
    val gridColor = MaterialTheme.colorScheme.outlineVariant
    Canvas(modifier.fillMaxWidth().height(height)) {
        val max = (values.maxOrNull() ?: 0.0).takeIf { it > 0 } ?: 1.0
        // Money labels like "Rs 2.01 Cr" are wider than the default gutter, so size it to the widest label.
        val widest = listOf(0.0, max / 2, max).maxOf { measurer.measure(format(it), labelStyle).size.width }
        val left = maxOf(AXIS_LABEL_SPACE_DP.dp.toPx(), widest + 6.dp.toPx())
        val top = 8.dp.toPx()
        val bottom = 22.dp.toPx()
        val w = size.width - left
        val h = size.height - top - bottom
        listOf(0.0, max / 2, max).forEach { v ->
            val yy = top + (h * (1 - v / max)).toFloat()
            drawLine(gridColor, Offset(left, yy), Offset(size.width, yy), strokeWidth = 1.dp.toPx())
            val text = measurer.measure(format(v), labelStyle)
            drawText(text, topLeft = Offset(0f, (yy - text.size.height / 2f).coerceIn(0f, size.height - text.size.height)))
        }
        val slot = w / values.size
        val barW = slot * 0.6f
        values.forEachIndexed { i, v ->
            val barH = (h * (v / max)).toFloat()
            drawRoundRect(
                color = if (i == values.lastIndex) color else color.copy(alpha = 0.45f),
                topLeft = Offset(left + slot * i + (slot - barW) / 2, top + h - barH),
                size = Size(barW, barH),
                cornerRadius = CornerRadius(3.dp.toPx()),
            )
        }
        listOf(0, values.lastIndex / 2, values.lastIndex).distinct().forEach { i ->
            val text = measurer.measure(labels[i], labelStyle)
            val cx = left + slot * i + slot / 2
            drawText(text, topLeft = Offset((cx - text.size.width / 2f).coerceIn(left, size.width - text.size.width), size.height - text.size.height))
        }
    }
}

/** Horizontal stacked bar, e.g. High / Medium / Low vehicle counts. */
@Composable
fun SegmentedBar(parts: List<Pair<Int, Color>>, modifier: Modifier = Modifier, height: Dp = 12.dp) {
    val visible = parts.filter { it.first > 0 }
    Row(modifier.fillMaxWidth().height(height).clip(MaterialTheme.shapes.small)) {
        if (visible.isEmpty()) {
            Box(Modifier.fillMaxWidth().fillMaxHeight().background(MaterialTheme.colorScheme.surfaceVariant))
        }
        visible.forEach { (count, color) ->
            Box(Modifier.weight(count.toFloat()).fillMaxHeight().background(color))
        }
    }
}
