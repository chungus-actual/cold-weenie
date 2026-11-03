package io.github.chungus_actual.coldweenie

import android.content.res.AssetManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.LightingColorFilter
import android.graphics.Paint
import android.graphics.Path
import android.graphics.PorterDuff
import android.graphics.PorterDuffXfermode
import android.graphics.RadialGradient
import android.graphics.Rect
import android.graphics.RectF
import android.graphics.Shader
import android.os.SystemClock
import kotlin.math.sin
import kotlin.random.Random

/** What moves in the rendered rooms: lava in the lamp, twinkling bulbs, steam off the pizza, riders on the grid. The rain has its own surface, RainGlass. */
class SceneLife(private val wall: Bitmap, private val assets: AssetManager? = null) {
    private val src = Rect()
    private val dst = RectF()
    private val blob = softBlob()
    private val glow = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG).apply {
        xfermode = PorterDuffXfermode(PorterDuff.Mode.ADD)
    }

    private val hasLamp = Geo.lampLow.isNotEmpty()
    private val glass = Path().apply {
        if (hasLamp) {
            moveTo(Geo.lampLow[0] - Geo.lampLow[2], Geo.lampLow[1])
            lineTo(Geo.lampTop[0] - Geo.lampTop[2], Geo.lampTop[1])
            lineTo(Geo.lampTop[0] + Geo.lampTop[2], Geo.lampTop[1])
            lineTo(Geo.lampLow[0] + Geo.lampLow[2], Geo.lampLow[1])
            close()
        }
    }
    private val waxes = arrayOf(
        floatArrayOf(.05f, .0f, .82f), floatArrayOf(.083f, 1.7f, .56f), floatArrayOf(.061f, 3.1f, .66f),
        floatArrayOf(.039f, 4.4f, .44f), floatArrayOf(.071f, 5.6f, .5f),
    )

    private val steam = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG).apply {
        colorFilter = LightingColorFilter(0xFFFFEEDC.toInt(), 0)
    }

    // heat: a patch of the room redrawn on a mesh that wobbles, pinned at its edges so it can't show a seam
    private val heatBox = if (Geo.steam.isEmpty()) Rect() else Rect(
        (Geo.steam.filterIndexed { i, _ -> i % 2 == 0 }.min() - 58f * Geo.steamSize).toInt(),
        (Geo.steam[1] - 175f * Geo.steamSize).toInt(),
        (Geo.steam.filterIndexed { i, _ -> i % 2 == 0 }.max() + 58f * Geo.steamSize).toInt(),
        (Geo.steam[1] - 26f * Geo.steamSize).toInt(),
    )
    private val heat = if (Geo.steam.isEmpty()) null else Bitmap.createBitmap(wall, heatBox.left, heatBox.top, heatBox.width(), heatBox.height())
    private val heatMesh = FloatArray((HEAT_W + 1) * (HEAT_H + 1) * 2)
    private val heatPaint = Paint(Paint.FILTER_BITMAP_FLAG)

    private fun softBlob(): Bitmap {
        val b = Bitmap.createBitmap(96, 96, Bitmap.Config.ARGB_8888)
        val cv = Canvas(b)
        val pp = Paint(Paint.ANTI_ALIAS_FLAG)
        pp.shader = RadialGradient(48f, 48f, 48f, intArrayOf(Color.WHITE, Color.WHITE, 0x00FFFFFF), floatArrayOf(0f, .55f, 1f), Shader.TileMode.CLAMP)
        cv.drawCircle(48f, 48f, 48f, pp)
        return b
    }

    fun behind(c: Canvas) {
        if (Geo.steam.isNotEmpty()) {
            drawHeat(c)
            drawSteam(c)
        }
        if (Geo.bulbs.isNotEmpty()) drawBulbs(c)
        if (Geo.runners.isNotEmpty()) drawRunners(c)
        if (Geo.passers.isNotEmpty()) drawPassers(c)
        if (Geo.claw.isNotEmpty()) drawClaw(c)
    }

    fun front(c: Canvas) {
        if (hasLamp) drawLava(c)
    }

    private val pictures = HashMap<String, Bitmap>()
    private fun picture(name: String): Bitmap? = pictures[name] ?: runCatching {
        assets!!.open("scenes/${Geo.name}/$name").use { BitmapFactory.decodeStream(it) }
    }.getOrNull()?.also { pictures[name] = it }

    private val plain = Paint(Paint.FILTER_BITMAP_FLAG or Paint.ANTI_ALIAS_FLAG)
    private val trail = Paint()
    private val cutout = Rect()

    private val metal = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = 0xFFAEB2BE.toInt()
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
    }
    private val metalDark = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF3C3E48.toInt() }
    private val prong = Path()

    private fun ease(f: Float): Float {
        val k = f.coerceIn(0f, 1f)
        return k * k * (3f - 2f * k)
    }

    /**
     * Over, down, shut, up, back. It mostly closes on nothing. Now and then it hooks the hot dog on top, carries it a little way,
     * and drops it at a height nobody can predict. It has never once got one to the chute.
     */
    private fun drawClaw(c: Canvas) {
        val g = Geo.claw
        val now = SystemClock.uptimeMillis() / 1000f + 22f
        val t = now % CLAW_EVERY
        val luck = Random((now / CLAW_EVERY).toInt())
        val hooks = luck.nextFloat() < .36f
        // when, on the way up, it lets go, and it's a different moment every time
        val slips = 9.8f + luck.nextFloat() * 2.9f
        var across = 0f
        var drop = 0f
        var shut = 0f
        var sway = 0f
        when {
            t < 5f -> across = ease(t / 5f)
            t < 8.5f -> { across = 1f; drop = ease((t - 5f) / 3.5f) }
            t < 9.4f -> { across = 1f; drop = 1f; shut = ease((t - 8.5f) / .9f) }
            t < 13f -> { across = 1f; drop = 1f - ease((t - 9.4f) / 3.6f); shut = if (hooks) .72f else 1f; sway = (13f - t) / 3.6f }
            t < 14f -> { across = 1f; shut = (if (hooks) .72f else 1f) * (1f - ease(t - 13f)) }
            t < 19f -> across = 1f - ease((t - 14f) / 5f)
        }
        val topX = g[0] + (g[4] - g[0]) * across
        val topY = g[1] + (g[5] - g[1]) * across
        val restX = g[2] + (g[6] - g[2]) * across
        val restY = g[3] + (g[7] - g[3]) * across
        val swing = sin((t * 3.1f).toDouble()).toFloat() * sway * 5f
        val headX = restX + (g[8] - g[6]) * drop + swing
        val headY = restY + (g[9] - g[7]) * drop
        val u = g[10]
        if (Geo.topDog.isNotEmpty()) drawTopDog(c, hooks, slips, t, headX - g[8], headY - g[9])
        metal.strokeWidth = u * .085f
        c.drawLine(topX, topY, headX, headY, metal)
        dst.set(headX - u * .17f, headY - u * .08f, headX + u * .17f, headY + u * .09f)
        c.drawRoundRect(dst, u * .04f, u * .04f, metalDark)
        metal.strokeWidth = u * .07f
        for (side in intArrayOf(-1, 0, 1)) {
            val bow = side * u * (.36f - .22f * shut)
            val tip = side * u * (.06f + .25f * (1f - shut))
            prong.reset()
            prong.moveTo(headX + side * u * .1f, headY + u * .06f)
            prong.quadTo(headX + bow, headY + u * .4f, headX + tip, headY + u * .78f)
            c.drawPath(prong, metal)
        }
    }

    /** It rides up with the claw, rocking, then falls under its own weight, bounces once, and lies where it always lay. */
    private fun drawTopDog(c: Canvas, hooks: Boolean, slips: Float, t: Float, offX: Float, offY: Float) {
        val dog = picture("topdog.png") ?: return
        val d = Geo.topDog
        var x = 0f
        var y = 0f
        var turn = 0f
        if (hooks && t > 9.4f) {
            if (t < slips) {
                x = offX
                y = offY
                turn = sin((t * 4.3f).toDouble()).toFloat() * 7f
            } else {
                // how high it was when it slipped, and how long gravity has had it
                val rise = 1f - ease((slips - 9.4f) / 3.6f)
                val high = (Geo.claw[3] - Geo.claw[9]).let { it * (1f - rise) * -1f }
                val startY = -high.let { if (it < 0f) -it else it }
                val since = t - slips
                val fallAt = 1100f
                val fallFor = Math.sqrt((2f * -startY / fallAt).toDouble()).toFloat()
                if (since < fallFor) {
                    y = startY + .5f * fallAt * since * since
                    turn = since * 95f
                } else if (since < fallFor + .34f) {
                    val b = (since - fallFor) / .34f
                    y = -4f * 15f * b * (1f - b)
                    turn = 14f * (1f - b)
                }
            }
        }
        val cx = d[0] + d[2] / 2 + x
        val cy = d[1] + d[3] / 2 + y
        src.set(0, 0, dog.width, dog.height)
        dst.set(cx - d[2] / 2, cy - d[3] / 2, cx + d[2] / 2, cy + d[3] / 2)
        c.save()
        c.rotate(turn, cx, cy)
        c.drawBitmap(dog, src, dst, plain)
        c.restore()
    }

    /**
     * A cycle crossing the far floor with its wall behind it, or the big M going over. Each path has its own picture of everything
     * nearer than it, laid back over the top, so they go behind what they should. Only loaded and drawn while something's crossing.
     */
    private fun drawPassers(c: Canvas) {
        val t = SystemClock.uptimeMillis() / 1000f
        for (p in Geo.passers) {
            val at = ((t - p.at) % p.every + p.every) % p.every
            val run = at / p.step
            val steps = p.path.size / 2 - 1
            if (run >= steps) continue
            val leg = run.toInt().coerceAtMost(steps - 1)
            val f = run - leg
            val x = p.path[leg * 2] + (p.path[leg * 2 + 2] - p.path[leg * 2]) * f
            val y = p.path[leg * 2 + 1] + (p.path[leg * 2 + 3] - p.path[leg * 2 + 1]) * f
            val goingRight = p.path[2] > p.path[0]
            val sprite = picture(p.sprite + ".png") ?: continue
            val h = p.tall * 1.25f
            val w = h * sprite.width / sprite.height
            var left = x - w / 2
            var right = x + w / 2
            if (p.wall != 0) {
                val tail = 44
                val wallH = p.tall * .5f
                var i = 1
                while (i <= tail) {
                    val k = leg - i
                    if (k < 0) break
                    val x0 = p.path[k * 2]
                    val x1 = p.path[k * 2 + 2]
                    trail.color = p.wall
                    trail.alpha = 215 - 215 * i / tail
                    c.drawRect(minOf(x0, x1), y - wallH, maxOf(x0, x1) + 1f, y, trail)
                    left = minOf(left, x0)
                    right = maxOf(right, x0)
                    i++
                }
            }
            src.set(0, 0, sprite.width, sprite.height)
            dst.set(x - w / 2, y - h * .96f, x + w / 2, y + h * .04f)
            c.save()
            if (!goingRight) c.scale(-1f, 1f, x, y)
            c.drawBitmap(sprite, src, dst, plain)
            c.restore()
            val near = picture(p.nearer) ?: continue
            cutout.set(left.toInt().coerceIn(0, near.width), (y - h - 8f).toInt().coerceIn(0, near.height), right.toInt().coerceIn(0, near.width), (y + 12f).toInt().coerceIn(0, near.height))
            if (!cutout.isEmpty) {
                dst.set(cutout)
                c.drawBitmap(near, cutout, dst, plain)
            }
        }
    }

    /** A bead of light and its tail, out along its path, gone for a while, and off again. */
    private fun drawRunners(c: Canvas) {
        val t = SystemClock.uptimeMillis() / 1000f
        src.set(0, 0, blob.width, blob.height)
        Geo.runners.forEachIndexed { k, r ->
            val lap = r.path.size / 2 * r.speed * 1.7f
            val at = (t + k * 7.3f) % lap
            val run = at / r.speed
            val legs = r.path.size / 2 - 1
            if (run >= legs) return@forEachIndexed
            glow.colorFilter = LightingColorFilter(r.color, 0)
            for (i in 0 until 9) {
                val back = run - i * .22f
                if (back < 0f) break
                val leg = back.toInt().coerceAtMost(legs - 1)
                if (!r.seen[leg] || !r.seen[leg + 1]) continue
                val f = back - leg
                val x = r.path[leg * 2] + (r.path[leg * 2 + 2] - r.path[leg * 2]) * f
                val y = r.path[leg * 2 + 1] + (r.path[leg * 2 + 3] - r.path[leg * 2 + 1]) * f
                val size = if (i == 0) 6f else 3.4f - i * .22f
                glow.alpha = 235 - i * 25
                dst.set(x - size, y - size * .7f, x + size, y + size * .7f)
                c.drawBitmap(blob, src, dst, glow)
            }
        }
    }

    private fun drawBulbs(c: Canvas) {
        val t = SystemClock.uptimeMillis() / 1000f
        src.set(0, 0, blob.width, blob.height)
        val colors = intArrayOf(0xFFFF4A3C.toInt(), 0xFFFFC23C.toInt(), 0xFF3CFF7A.toInt(), 0xFF3C9CFF.toInt())
        var i = 0
        while (i < Geo.bulbs.size) {
            val k = i / 2
            val phase = t * (.6f + (k % 5) * .13f) + k * 1.3f
            val a = .55f + .45f * sin(phase.toDouble()).toFloat()
            glow.colorFilter = LightingColorFilter(colors[k % colors.size], 0)
            glow.alpha = (a * 255).toInt().coerceIn(0, 255)
            val x = Geo.bulbs[i]
            val y = Geo.bulbs[i + 1]
            dst.set(x - 13f, y - 13f, x + 13f, y + 13f)
            c.drawBitmap(blob, src, dst, glow)
            i += 2
        }
    }

    /** Slow wax. Lit from inside by the bulb, so it brightens at the bottom. */
    private fun drawLava(c: Canvas) {
        val t = SystemClock.uptimeMillis() / 1000f
        val lx = Geo.lampLow[0]
        val ly = Geo.lampLow[1]
        val lr = Geo.lampLow[2]
        val tx = Geo.lampTop[0]
        val ty = Geo.lampTop[1]
        val tr = Geo.lampTop[2]
        c.save()
        c.clipPath(glass)
        src.set(0, 0, blob.width, blob.height)
        glow.colorFilter = LightingColorFilter(0xFFFF8AD8.toInt(), 0)
        glow.alpha = 255
        dst.set(lx - lr * 1.25f, ly - lr * .75f, lx + lr * 1.25f, ly + lr * .75f)
        c.drawBitmap(blob, src, dst, glow)
        for (b in waxes) {
            val h = .5f + .5f * sin((t * b[0] * 2.2f + b[1]).toDouble()).toFloat()
            val y = ly + (ty - ly) * h
            val w = lr + (tr - lr) * h
            val x = lx + (tx - lx) * h + w * .28f * sin((t * .31f + b[1] * 2f).toDouble()).toFloat()
            val r = w * b[2] * (1f + .12f * sin((t * .7f + b[1]).toDouble()).toFloat())
            dst.set(x - r, y - r * 1.2f, x + r, y + r * 1.2f)
            glow.alpha = (235 - h * 90).toInt()
            c.drawBitmap(blob, src, dst, glow)
        }
        c.restore()
    }

    private fun drawHeat(c: Canvas) {
        val t = SystemClock.uptimeMillis() / 1000f
        val w = heatBox.width().toFloat()
        val h = heatBox.height().toFloat()
        var k = 0
        for (j in 0..HEAT_H) {
            val v = j.toFloat() / HEAT_H
            // strongest a little way over the crust; nothing moves at the pie itself or by the top
            val rise = sin((v * Math.PI).toFloat().toDouble()).toFloat()
            for (i in 0..HEAT_W) {
                val u = i.toFloat() / HEAT_W
                val edge = sin((u * Math.PI).toFloat().toDouble()).toFloat()
                val a = rise * edge * 1.15f
                val dx = sin((v * 26f + t * 5.1f + u * 3f).toDouble()).toFloat() * a + sin((v * 11f - t * 3.3f + u * 7f).toDouble()).toFloat() * a * .6f
                val dy = sin((u * 17f + t * 4.3f + v * 9f).toDouble()).toFloat() * a * .45f
                heatMesh[k++] = heatBox.left + u * w + dx
                heatMesh[k++] = heatBox.top + v * h + dy
            }
        }
        c.drawBitmapMesh(heat!!, HEAT_W, HEAT_H, heatMesh, 0, null, 0, heatPaint)
    }

    /** A wisp off the pie, thin at the source, wandering and thinning out as it climbs. */
    private fun drawSteam(c: Canvas) {
        val t = SystemClock.uptimeMillis() / 1000f
        src.set(0, 0, blob.width, blob.height)
        var w = 0
        while (w < Geo.steam.size) {
            val k = w / 2
            for (i in 0 until 16) {
                val age = (t * (.17f + k * .025f) + i / 16f + k * .37f) % 1f
                val y = Geo.steam[w + 1] - (14f + age * 118f) * Geo.steamSize
                val sway = sin((age * 5.2f - t * .9f + k * 2.1f).toDouble()).toFloat() * (1.5f + age * 11f) * Geo.steamSize +
                    sin((age * 11f + t * .5f + k).toDouble()).toFloat() * age * 6f * Geo.steamSize
                val r = (4f + age * 17f) * Geo.steamSize
                val x = Geo.steam[w] + sway
                steam.alpha = (sin(Math.PI * Math.pow(age.toDouble(), .62)).toFloat() * (21f / Geo.steamSize)).toInt().coerceIn(0, 255)
                dst.set(x - r * .8f, y - r * 1.15f, x + r * .8f, y + r * 1.15f)
                c.drawBitmap(blob, src, dst, steam)
            }
            w += 2
        }
    }

    private companion object {
        const val HEAT_W = 14
        const val HEAT_H = 22
        const val CLAW_EVERY = 64f
    }
}
