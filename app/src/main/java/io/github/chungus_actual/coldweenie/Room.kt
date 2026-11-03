package io.github.chungus_actual.coldweenie

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.LightingColorFilter
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.PorterDuff
import android.graphics.PorterDuffXfermode
import android.graphics.Rect
import android.graphics.RectF
import android.graphics.Typeface
import android.os.SystemClock
import android.text.format.DateUtils
import android.view.KeyEvent
import android.view.View
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.random.Random

/**
 * The whole screen, drawn in 1920x1080 units: paneling, the TV, the shelves. Everything but the
 * picture itself (Crt, behind this view) happens here.
 */
class Room(context: Context, private val crt: Crt, private val host: Host) : View(context) {
    interface Host {
        fun play(g: Game, disc: Int)
        fun leave()
        fun sound(name: String)
        /** Hand off to the system's voice input, if the box has one. */
        fun listen()
        val canListen: Boolean
    }

    private fun asset(name: String): Bitmap = context.assets.open(name).use { BitmapFactory.decodeStream(it) }
    private val wall = asset("scenes/${Geo.name}/room.jpg")
    private val tvLight = asset("scenes/${Geo.name}/tvlight.jpg")
    private val shelf = asset("shelf.png")
    private val glassMask = if (Geo.glass.isNotEmpty()) asset("scenes/${Geo.name}/glass.png") else null
    private val dialPlate = asset("dial_plate.png")
    private val dialKnob = asset("dial_knob.png")
    private val dialShine = asset("dial_shine.png")
    private val searchTile = asset("search_tile.png")
    private val statsTile = asset("stats_tile.png")
    private val marker = Typeface.createFromAsset(context.assets, "fonts/PermanentMarker.ttf")
    private val vcr = Typeface.createFromAsset(context.assets, "fonts/VT323.ttf")

    private val art = Art { postInvalidateOnAnimation() }
    private val p = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG)
    private val clear = Paint(Paint.ANTI_ALIAS_FLAG).apply { xfermode = PorterDuffXfermode(PorterDuff.Mode.CLEAR) }
    private val add = Paint(Paint.FILTER_BITMAP_FLAG).apply { xfermode = PorterDuffXfermode(PorterDuff.Mode.ADD) }
    private val cut = Paint(Paint.FILTER_BITMAP_FLAG).apply { xfermode = PorterDuffXfermode(PorterDuff.Mode.DST_OUT) }
    private val tube = Geo.tubePath()
    private val osdMatrix = Matrix().apply {
        setPolyToPoly(floatArrayOf(0f, 0f, 640f, 0f, 640f, 480f, 0f, 480f), 0, Geo.screen, 0, 4)
    }
    private val life = SceneLife(wall, context.assets)
    private val src = Rect()
    private val dst = RectF()

    private val pages = ArrayList<Page>()
    private val page get() = pages.last()
    private var lift = 1f
    private var liftKey: Any? = null
    private var ghost: Item? = null
    private var ghostLift = 0f
    private var osdUntil = 0L
    private var osd = ""
    private var pick: Game? = null
    private var spinLeft = 0
    /** Where the channel knob points, degrees, always turning one way. */
    private var dial = 0f
    private var dialTo = 0f
    /** Set while the search page is up; kb is whether focus is on the keys rather than the results. */
    private var box: SearchBox? = null
    private var kb = true
    private var menu: Menu? = null
    private var ready = false

    private class Menu(val game: Game, val entries: List<Pair<String, () -> Unit>>) {
        var index = 0
    }

    private val noPicture = Runnable { retune() }

    fun show(home: Page) {
        pages.clear()
        pages += home
        ready = true
        retune()
        invalidate()
    }

    /** Back from a game: the shelves may have changed, but stay on the same one. */
    fun refresh(home: Page) {
        val depth = pages.size
        if (depth == 1) {
            pages[0] = home
            home.rowIndex = 0
        } else if (page.log != null) {
            val rows = page.rowIndex
            pages[depth - 1] = Rows.stats().also {
                it.rowIndex = rows.coerceIn(0, it.rows.size - 1)
                it.rowScroll = it.rowIndex.toFloat()
            }
        }
        ready = true
        retune()
        invalidate()
    }

    private val row get() = page.rows[page.rowIndex.coerceIn(0, page.rows.size - 1)]
    private val item: Item? get() = row.items.getOrNull(row.index)
    private fun heroGame(): Game? = pick ?: (item as? Item.Play)?.game

    // ---- layout -----------------------------------------------------------------------------

    private fun tileWidth(i: Item): Float = when (i) {
        is Item.Play -> if (i.resume && Launcher.resumeFrame(i.game) != null) TILE_H * 4f / 3f else TILE_H * i.game.aspect
        is Item.Spin, Item.Search, Item.Stats -> TILE_H * .78f
        is Item.Console -> 340f
        is Item.Genre -> 300f
    }

    private fun xOf(r: Row, index: Int): Float {
        var x = 0f
        for (k in 0 until index) x += tileWidth(r.items[k]) + GAP
        return x
    }

    private fun aim(r: Row) {
        val x = xOf(r, r.index)
        r.scrollTo = max(0f, x - (if (r.index == 0) 0f else 150f))
    }

    // ---- input ------------------------------------------------------------------------------

    fun key(code: Int, repeat: Int): Boolean {
        if (!ready) return false
        menu?.let { return menuKey(it, code) }
        box?.let { b -> if (searchKey(b, code, repeat)) { invalidate(); return true } }
        if (entered(code, repeat)) return true
        when (code) {
            KeyEvent.KEYCODE_DPAD_LEFT -> move(-1)
            KeyEvent.KEYCODE_DPAD_RIGHT -> move(1)
            KeyEvent.KEYCODE_DPAD_UP -> rowMove(-1)
            KeyEvent.KEYCODE_DPAD_DOWN -> rowMove(1)
            KeyEvent.KEYCODE_BUTTON_L1, KeyEvent.KEYCODE_MEDIA_REWIND -> move(-6)
            KeyEvent.KEYCODE_BUTTON_R1, KeyEvent.KEYCODE_MEDIA_FAST_FORWARD -> move(6)
            KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER, KeyEvent.KEYCODE_BUTTON_A, KeyEvent.KEYCODE_BUTTON_START -> if (repeat == 0) activate()
            KeyEvent.KEYCODE_BACK, KeyEvent.KEYCODE_BUTTON_B -> if (repeat == 0) back()
            KeyEvent.KEYCODE_BUTTON_Y, KeyEvent.KEYCODE_PROG_YELLOW -> if (repeat == 0 && page.log == null) spin(page.pool)
            KeyEvent.KEYCODE_BUTTON_X, KeyEvent.KEYCODE_MENU -> if (repeat == 0) openMenu()
            KeyEvent.KEYCODE_SEARCH -> if (repeat == 0) {
                if (box == null) openSearch()
                host.listen()
            }
            KeyEvent.KEYCODE_BUTTON_SELECT -> if (repeat == 0) {
                crt.setMute(!crt.muted)
                osdShow(if (crt.muted) "MUTE" else "SOUND ON", 1800)
            }
            else -> return false
        }
        invalidate()
        return true
    }

    private var codeAt = 0
    private val heldBack = Runnable {
        codeAt = 0
        back()
        invalidate()
    }

    /**
     * Up up down down left right left right B A. The directions still move you, but B would leave and A would launch, so once
     * the eight are in, B waits a moment to see whether A follows. True when the key was taken.
     */
    private fun entered(code: Int, repeat: Int): Boolean {
        if (repeat != 0) return false
        val isB = code == KeyEvent.KEYCODE_BACK || code == KeyEvent.KEYCODE_BUTTON_B
        val isA = code == KeyEvent.KEYCODE_DPAD_CENTER || code == KeyEvent.KEYCODE_ENTER || code == KeyEvent.KEYCODE_BUTTON_A
        when {
            codeAt == CODE.size + 1 -> {
                removeCallbacks(heldBack)
                codeAt = 0
                if (isA) {
                    thirtyLives()
                    return true
                }
                back()
                return false
            }
            codeAt == CODE.size -> {
                if (isB) {
                    codeAt++
                    postDelayed(heldBack, 900)
                    return true
                }
                codeAt = if (code == CODE[0]) 1 else 0
            }
            code == CODE[codeAt] -> codeAt++
            codeAt == 2 && code == CODE[0] -> Unit
            else -> codeAt = if (code == CODE[0]) 1 else 0
        }
        return false
    }

    private fun thirtyLives() {
        Rows.thirtyLives = true
        while (pages.size > 1) pages.removeAt(pages.size - 1)
        cancelSpin()
        lift = 0f
        ghost = null
        refresh(Rows.home())
        crt.burst()
        osdShow("CH 30", 6000)
        host.sound("thunk")
        invalidate()
    }

    private fun cancelSpin() {
        if (spinLeft > 0 || pick != null) {
            spinLeft = 0
            pick = null
            removeCallbacks(spinStep)
        }
    }

    private fun move(d: Int) {
        cancelSpin()
        val r = row
        val n = (r.index + d).coerceIn(0, r.items.size - 1)
        if (n == r.index) return
        ghost = r.items[r.index]
        ghostLift = lift
        r.index = n
        aim(r)
        focusChanged()
    }

    private fun rowMove(d: Int) {
        cancelSpin()
        val n = (page.rowIndex + d).coerceIn(0, page.rows.size - 1)
        if (n == page.rowIndex) return
        ghost = null
        val oldX = xOf(row, row.index) - row.scroll
        page.rowIndex = n
        // land on whatever is under your eye in the new row
        val r = row
        var best = r.index
        var bestD = Float.MAX_VALUE
        for (k in r.items.indices) {
            val dx = abs(xOf(r, k) - r.scroll - oldX)
            if (dx < bestD) {
                bestD = dx
                best = k
            }
        }
        r.index = best
        aim(r)
        focusChanged()
    }

    private fun focusChanged() {
        lift = 0f
        host.sound("tick")
        removeCallbacks(noPicture)
        // on the stats page the set is showing the chart, whatever's on the shelf
        if (page.log != null) return
        crt.burst()
        postDelayed(noPicture, 260)
    }

    private fun retune() {
        val i = item
        when {
            page.log != null -> crt.tune(null)
            pick != null -> tuneGame(pick!!)
            i is Item.Play -> tuneGame(i.game)
            i is Item.Console -> {
                crt.tune(Catalog.menuVideo[i.sys.db.lowercase()], Random.nextFloat() * .8f)
                osdShow("CH ${"%02d".format(i.sys.channel)}", 2600)
            }
            i is Item.Genre -> {
                crt.tune(null)
                osdShow(i.name.uppercase(), 2600)
            }
            i is Item.Spin -> {
                crt.tune(null)
                osdShow("SCAN >>", 2600)
            }
            i === Item.Search -> {
                crt.tune(null)
                osdShow("SEARCH", 2600)
            }
            i === Item.Stats -> {
                crt.tune(null)
                osdShow("STATS", 2600)
            }
            else -> crt.tune(null)
        }
    }

    private fun tuneGame(g: Game) {
        if (page.log != null) return
        crt.tune(g.video)
        osdShow("CH ${"%02d".format(g.sys.channel)}", 2600)
    }

    private fun osdShow(s: String, ms: Long) {
        osd = s
        osdUntil = SystemClock.uptimeMillis() + ms
    }

    private fun activate() {
        pick?.let { launch(it, Stats.disc(it)); return }
        when (val i = item) {
            is Item.Play -> launch(i.game, Stats.disc(i.game))
            is Item.Spin -> spin(i.pool)
            Item.Search -> openSearch()
            Item.Stats -> push(Rows.stats())
            is Item.Console -> push(Rows.console(i.sys))
            is Item.Genre -> push(Rows.genre(i.name))
            null -> {}
        }
    }

    private fun push(next: Page) {
        host.sound("thunk")
        pages += next
        lift = 0f
        ghost = null
        retune()
    }

    private fun back() {
        if (pick != null) {
            cancelSpin()
            retune()
            return
        }
        if (pages.size > 1) {
            host.sound("back")
            pages.removeAt(pages.size - 1)
            lift = 0f
            ghost = null
            retune()
        } else {
            host.leave()
        }
    }

    private fun launch(g: Game, disc: Int) {
        host.sound("power")
        crt.burst()
        host.play(g, disc)
    }

    // ---- spin the dial ----------------------------------------------------------------------

    private val spinStep = object : Runnable {
        override fun run() {
            val pool = spinPool
            if (spinLeft <= 0 || pool.isEmpty()) return
            spinLeft--
            val g = pool[Random.nextInt(pool.size)]
            pick = g
            host.sound(if (spinLeft == 0) "thunk" else "tick")
            crt.burst()
            osdShow("CH ${"%02d".format(g.sys.channel)}", 2600)
            dialTo += 30f * (1 + Random.nextInt(11))
            if (spinLeft == 0) {
                tuneGame(g)
            } else {
                postDelayed(this, 70L + (11 - spinLeft) * (11 - spinLeft) * 3L)
            }
            invalidate()
        }
    }
    private var spinPool: List<Game> = emptyList()

    private fun spin(pool: List<Game>) {
        if (pool.isEmpty()) return
        spinPool = pool
        spinLeft = 11
        removeCallbacks(noPicture)
        removeCallbacks(spinStep)
        crt.tune(null)
        post(spinStep)
    }

    // ---- search -----------------------------------------------------------------------------

    private fun openSearch() {
        host.sound("thunk")
        val b = SearchBox(Catalog.games)
        box = b
        kb = true
        pages += Rows.search(b)
        lift = 0f
        ghost = null
        retune()
    }

    private fun closeSearch() {
        box = null
        host.sound("back")
        pages.removeAt(pages.size - 1)
        lift = 0f
        ghost = null
        retune()
    }

    /** The letters changed: new results on the shelf, and the TV catches up once you pause. */
    private fun searched(b: SearchBox) {
        pages[pages.size - 1] = Rows.search(b)
        host.sound("tick")
        ghost = null
        removeCallbacks(noPicture)
        crt.burst()
        // where the name came from. Would you rather be a cold weenie or a real hot dog?
        val theAd = java.io.File(Stats.dir, "hotdog.mp4")
        if (b.query.filter { it.isLetter() }.equals("hotdog", ignoreCase = true) && theAd.isFile) {
            crt.tune(theAd.path)
            osdShow("REAL HOT DOG", 9000)
            return
        }
        postDelayed(noPicture, 380)
    }

    /** What the system's voice input heard. */
    fun heard(text: String) {
        val b = box ?: return
        b.set(text)
        searched(b)
        kb = b.results.isEmpty()
        lift = 0f
        invalidate()
    }

    private fun searchKey(b: SearchBox, code: Int, repeat: Int): Boolean {
        when (code) {
            in KeyEvent.KEYCODE_A..KeyEvent.KEYCODE_Z -> b.type('a' + (code - KeyEvent.KEYCODE_A))
            in KeyEvent.KEYCODE_0..KeyEvent.KEYCODE_9 -> b.type('0' + (code - KeyEvent.KEYCODE_0))
            KeyEvent.KEYCODE_SPACE -> b.type(' ')
            KeyEvent.KEYCODE_DEL -> b.erase()
            else -> return if (kb) keysKey(b, code, repeat) else resultsKey(code)
        }
        searched(b)
        return true
    }

    private fun keysKey(b: SearchBox, code: Int, repeat: Int): Boolean {
        when (code) {
            KeyEvent.KEYCODE_DPAD_LEFT -> if (b.move(-1, 0)) host.sound("tick")
            KeyEvent.KEYCODE_DPAD_RIGHT -> if (b.move(1, 0)) host.sound("tick")
            KeyEvent.KEYCODE_DPAD_UP -> if (b.move(0, -1)) host.sound("tick")
            KeyEvent.KEYCODE_DPAD_DOWN -> if (b.move(0, 1)) host.sound("tick") else if (row.items.isNotEmpty()) {
                kb = false
                lift = 0f
                host.sound("tick")
            }
            KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER, KeyEvent.KEYCODE_BUTTON_A -> if (repeat == 0) {
                b.pick()
                searched(b)
            }
            KeyEvent.KEYCODE_BACK, KeyEvent.KEYCODE_BUTTON_B -> if (repeat == 0) {
                if (b.query.isEmpty()) closeSearch() else {
                    b.erase()
                    searched(b)
                }
            }
            KeyEvent.KEYCODE_BUTTON_Y, KeyEvent.KEYCODE_SEARCH -> if (repeat == 0 && host.canListen) host.listen()
            else -> return false
        }
        return true
    }

    private fun resultsKey(code: Int): Boolean {
        when (code) {
            KeyEvent.KEYCODE_DPAD_UP, KeyEvent.KEYCODE_BACK, KeyEvent.KEYCODE_BUTTON_B -> {
                cancelSpin()
                kb = true
                host.sound("tick")
            }
            KeyEvent.KEYCODE_SEARCH -> if (host.canListen) host.listen()
            else -> return false
        }
        return true
    }

    private fun drawSearch(c: Canvas, b: SearchBox) {
        // what you've typed, on tape, with a blinking cursor while the keys have focus
        val blink = kb && (SystemClock.uptimeMillis() / 500) % 2 == 0L
        val text = b.query.uppercase() + if (blink) "_" else ""
        val tw = max(380f, measure(b.query.uppercase() + "_", 66f, marker) + 44f)
        c.save()
        c.rotate(-.7f, LEFT, 110f)
        p.color = TAPE
        p.style = Paint.Style.FILL
        dst.set(LEFT, 52f, LEFT + min(tw, 980f), 138f)
        c.drawRect(dst, p)
        label(c, text, LEFT + 22f, 118f, 66f, INK, marker)
        c.restore()

        // the keys, on a dark plate
        val ox = LEFT
        val oy = 166f
        p.color = 0xC8100C0A.toInt()
        dst.set(ox - 10f, oy - 10f, ox + SearchBox.COLS * KEY + 4f, oy + SearchBox.ROWS * KEY + 4f)
        c.drawRoundRect(dst, 14f, 14f, p)
        b.cells.forEachIndexed { i, k ->
            val x = ox + k.col * KEY
            val y = oy + k.row * KEY
            val on = kb && i == b.focus
            val grow = if (on) 7f else 0f
            dst.set(x - grow, y - grow, x + KEY - 6f + grow, y + KEY - 6f + grow)
            p.style = Paint.Style.FILL
            p.color = when {
                k.hub -> 0xFF3A2A4A.toInt()
                else -> blend(0xFF6B6250.toInt(), 0xFFE9DCB8.toInt(), .25f + k.strength * .75f)
            }
            c.drawRoundRect(dst, 9f, 9f, p)
            val face = if (k.ch == ' ') "__" else k.ch.uppercaseChar().toString()
            centered(c, face, x + (KEY - 6f) / 2f, y + KEY - 24f, 50f, if (k.hub) BONE else INK, marker, 255)
            if (on) {
                p.style = Paint.Style.STROKE
                p.strokeWidth = 5f
                p.color = NEON
                c.drawRoundRect(dst, 9f, 9f, p)
                p.style = Paint.Style.FILL
            }
        }

        // what you're about to get, and the buttons
        val g = heroGame()
        val rx = ox + SearchBox.COLS * KEY + 30f
        if (g != null) {
            val wheel = art.get(g.wheel, 320)
            if (wheel != null) {
                val k = min(430f / wheel.width, 150f / wheel.height)
                dst.set(rx, 210f - wheel.height * k, rx + wheel.width * k, 210f)
                src.set(0, 0, wheel.width, wheel.height)
                p.alpha = 255
                c.drawBitmap(wheel, src, dst, p)
            } else {
                wrapped(c, g.title, rx, 110f, 430f, 44f, 255, BONE)
            }
            label(c, listOf(g.year, g.sys.label).filter { it.isNotBlank() }.joinToString("   "), rx, 262f, 44f, AMBER, vcr)
        }
        var by = 400f
        if (kb) {
            button(c, "A", BTN_A, "Pick", rx, by); by += 60f
            button(c, "B", BTN_B, if (b.query.isEmpty()) "Back" else "Erase", rx, by); by += 60f
            if (host.canListen) button(c, "Y", BTN_Y, "Say it", rx, by)
        } else {
            button(c, "A", BTN_A, if (g != null && Launcher.hasResume(g, Stats.disc(g))) "Continue" else "Play", rx, by); by += 60f
            button(c, "B", BTN_B, "Letters", rx, by)
        }
        if (kb) postInvalidateDelayed(120)
    }

    private fun blend(a: Int, b: Int, t: Float): Int = Color.rgb(
        (Color.red(a) + (Color.red(b) - Color.red(a)) * t).toInt(),
        (Color.green(a) + (Color.green(b) - Color.green(a)) * t).toInt(),
        (Color.blue(a) + (Color.blue(b) - Color.blue(a)) * t).toInt(),
    )

    // ---- options ----------------------------------------------------------------------------

    private fun openMenu() {
        val g = heroGame() ?: return
        val e = ArrayList<Pair<String, () -> Unit>>()
        val disc = Stats.disc(g)
        e += (if (Launcher.hasResume(g, disc)) "Continue" else "Play") to { launch(g, disc) }
        if (Launcher.hasResume(g, disc)) e += "Start over" to {
            Launcher.setAsideResume(g, disc)
            launch(g, disc)
        }
        if (g.discs.size > 1) for (d in g.discs.indices) if (d != disc) e += "Disc ${d + 1}" to { launch(g, d) }
        e += (if (Stats.favorite(g)) "Take off favorites" else "Add to favorites") to { Stats.toggleFavorite(g) }
        for ((shelf, label) in SHELVES) if (g.shelf != shelf) e += label to { reshelve(g, shelf) }
        menu = Menu(g, e)
        host.sound("thunk")
    }

    /** Stays where you are. The home screen behind you catches up, and any other page next time it's opened. */
    private fun reshelve(g: Game, shelf: String) {
        Stats.setShelf(g, shelf)
        Catalog.reshelve()
        val old = pages[0]
        val fresh = Rows.home()
        fresh.rowIndex = fresh.rows.indexOfFirst { it.title == old.rows.getOrNull(old.rowIndex)?.title }.coerceAtLeast(0)
        fresh.rowScroll = fresh.rowIndex.toFloat()
        for (r in fresh.rows) old.rows.firstOrNull { it.title == r.title }?.let { o ->
            r.index = o.index.coerceAtMost(r.items.size - 1)
            r.scroll = o.scroll
            r.scrollTo = o.scrollTo
        }
        pages[0] = fresh
        host.sound("thunk")
    }

    private fun menuKey(m: Menu, code: Int): Boolean {
        when (code) {
            KeyEvent.KEYCODE_DPAD_UP -> {
                m.index = (m.index - 1).coerceAtLeast(0)
                host.sound("tick")
            }
            KeyEvent.KEYCODE_DPAD_DOWN -> {
                m.index = (m.index + 1).coerceAtMost(m.entries.size - 1)
                host.sound("tick")
            }
            KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER, KeyEvent.KEYCODE_BUTTON_A -> {
                menu = null
                m.entries[m.index].second()
            }
            KeyEvent.KEYCODE_BACK, KeyEvent.KEYCODE_BUTTON_B, KeyEvent.KEYCODE_BUTTON_X, KeyEvent.KEYCODE_MENU -> {
                menu = null
                host.sound("back")
            }
            else -> return true
        }
        invalidate()
        return true
    }

    // ---- drawing ----------------------------------------------------------------------------

    override fun onDraw(c: Canvas) {
        val s = width / 1920f
        c.save()
        c.scale(s, s)
        p.alpha = 255
        c.drawBitmap(wall, 0f, 0f, p)
        life.behind(c)
        drawTvLight(c)
        c.drawPath(tube, clear)
        glassMask?.let {
            dst.set(Geo.glass[0], Geo.glass[1], Geo.glass[0] + Geo.glass[2], Geo.glass[1] + Geo.glass[3])
            c.drawBitmap(it, null, dst, cut)
        }
        life.front(c)
        if (ready && page.rows.isNotEmpty()) {
            val animating = stepAnimations()
            drawShelves(c)
            val b = box
            val l = page.log
            if (b != null) drawSearch(c, b) else if (l != null) drawStats(c, l) else drawHero(c)
            drawOsd(c)
            drawTapeNote(c)
            menu?.let { drawMenu(c, it) }
            if (animating || SystemClock.uptimeMillis() < osdUntil + 400) postInvalidateOnAnimation()
            else postInvalidateDelayed(33)
        } else {
            label(c, "Finding the games", 70f, 230f, 64f, BONE, marker)
            postInvalidateDelayed(33)
        }
        c.restore()
    }

    /** The game's own light on the room: the TV-only render, tinted by what's on the tube. */
    private fun drawTvLight(c: Canvas) {
        val k = 1.15f
        val col = Color.rgb(
            (crt.glowR * k * 255).toInt().coerceIn(0, 255),
            (crt.glowG * k * 255).toInt().coerceIn(0, 255),
            (crt.glowB * k * 255).toInt().coerceIn(0, 255),
        )
        add.colorFilter = LightingColorFilter(col, 0)
        src.set(0, 0, tvLight.width, tvLight.height)
        dst.set(0f, 0f, 1920f, 1080f)
        c.drawBitmap(tvLight, src, dst, add)
    }

    private fun approach(v: Float, t: Float, k: Float = .24f): Float = if (abs(t - v) < .5f) t else v + (t - v) * k

    private fun stepAnimations(): Boolean {
        var moving = false
        val r = row
        if (lift < 1f) {
            lift = min(1f, lift + .16f)
            moving = true
        }
        if (ghostLift > 0f) {
            ghostLift = max(0f, ghostLift - .18f)
            moving = true
        }
        val rt = page.rowIndex.toFloat()
        if (page.rowScroll != rt) {
            val d = rt - page.rowScroll
            page.rowScroll = if (abs(d) < .004f) rt else page.rowScroll + d * .24f
            moving = true
        }
        if (r.scroll != r.scrollTo) {
            r.scroll = approach(r.scroll, r.scrollTo)
            moving = true
        }
        if (dial != dialTo) {
            dial = approach(dial, dialTo, .3f)
            moving = true
        }
        return moving
    }

    private fun drawShelves(c: Canvas) {
        val top = ROWS_Y - 34f
        c.save()
        c.clipRect(0f, top, 1920f, 1080f)
        val first = max(0, page.rowIndex - 1)
        for (ri in first until min(page.rows.size, page.rowIndex + 3)) {
            val y = ROWS_Y + (ri - page.rowScroll) * ROW_PITCH
            if (y > 1080f || y < top - ROW_PITCH) continue
            drawRow(c, page.rows[ri], y, ri == page.rowIndex && !(box != null && kb))
        }
        c.restore()
    }

    private fun drawRow(c: Canvas, r: Row, y: Float, focused: Boolean) {
        val floor = y + 322f
        p.alpha = 255
        src.set(0, 0, shelf.width, shelf.height)
        dst.set(0f, floor - 4f, 1920f, floor - 4f + shelf.height)
        c.drawBitmap(shelf, src, dst, p)

        var x = LEFT - r.scroll
        val dim = if (focused) 255 else 150
        val fx: Item? = if (focused) r.items.getOrNull(r.index) else null
        var fxX = 0f
        for (it in r.items) {
            val w = tileWidth(it)
            if (x + w > -40f && x < 1960f) {
                if (it === fx) {
                    fxX = x
                } else {
                    val l = if (it === ghost) ghostLift else 0f
                    drawTile(c, it, x, floor, w, l, dim)
                }
            }
            x += w + GAP
        }
        fx?.let { drawTile(c, it, fxX, floor, tileWidth(it), lift, 255) }
        tape(c, r.title, LEFT - 6f, y, if (focused) 255 else 190)
    }

    private fun drawTile(c: Canvas, it: Item, x: Float, floor: Float, w: Float, l: Float, alpha: Int) {
        val eased = l * l * (3 - 2 * l)
        val sc = 1f + .09f * eased
        val tw = w * sc
        val th = TILE_H * sc
        val left = x - (tw - w) / 2f
        val top = floor - th - 8f * eased
        // contact shadow on the shelf
        p.style = Paint.Style.FILL
        p.color = Color.BLACK
        p.alpha = (alpha * .55f).toInt()
        dst.set(left + 6f, floor - 6f, left + tw - 2f, floor + 6f)
        c.drawOval(dst, p)
        when (it) {
            is Item.Play -> drawGame(c, it, left, top, tw, th, alpha)
            is Item.Spin -> drawSpin(c, left, top, tw, th, alpha)
            Item.Search -> {
                dst.set(left, top, left + tw, top + th)
                p.alpha = alpha
                c.drawBitmap(searchTile, null, dst, p)
            }
            Item.Stats -> {
                dst.set(left, top, left + tw, top + th)
                p.alpha = alpha
                c.drawBitmap(statsTile, null, dst, p)
                val secs = Stats.total
                val digits = "%04d:%02d".format(secs / 3600, (secs % 3600) / 60)
                centered(c, digits, left + tw / 2f, top + th * .285f, th * .165f, PHOSPHOR, vcr, alpha)
            }
            is Item.Console -> drawConsole(c, it, left, top, tw, th, alpha)
            is Item.Genre -> drawGenre(c, it, left, top, tw, th, alpha)
        }
        if (eased > .02f) {
            p.style = Paint.Style.STROKE
            p.strokeWidth = 5f
            p.color = NEON
            p.alpha = (255 * eased).toInt()
            dst.set(left - 6f, top - 6f, left + tw + 6f, top + th + 6f)
            c.drawRoundRect(dst, 7f, 7f, p)
            p.strokeWidth = 12f
            p.alpha = (56 * eased).toInt()
            dst.set(left - 11f, top - 11f, left + tw + 11f, top + th + 11f)
            c.drawRoundRect(dst, 12f, 12f, p)
            p.style = Paint.Style.FILL
        }
        p.alpha = 255
    }

    private fun drawGame(c: Canvas, it: Item.Play, left: Float, top: Float, w: Float, h: Float, alpha: Int) {
        val g = it.game
        val frame = if (it.resume) Launcher.resumeFrame(g) else null
        val bmp = if (frame != null) art.get(frame, 480) else art.get(g.box, 320)
        dst.set(left, top, left + w, top + h)
        if (bmp != null) {
            p.alpha = alpha
            src.set(0, 0, bmp.width, bmp.height)
            c.drawBitmap(bmp, src, dst, p)
        } else {
            // no art: a blank tape with the title in marker
            p.color = 0xFF2B2622.toInt()
            p.alpha = alpha
            c.drawRoundRect(dst, 4f, 4f, p)
            p.color = TAPE
            p.alpha = alpha
            dst.set(left + 12f, top + 26f, left + w - 12f, top + h - 26f)
            c.drawRect(dst, p)
            wrapped(c, g.title, left + 22f, top + 74f, w - 44f, 30f, alpha)
        }
        if (frame != null) {
            // the box leans on the corner of the frame you left off on
            val box = art.get(g.box, 320)
            if (box != null) {
                val bh = h * .46f
                val bw = bh * box.width / box.height
                dst.set(left + w - bw - 12f, top + h - bh - 10f, left + w - 12f, top + h - 10f)
                src.set(0, 0, box.width, box.height)
                p.alpha = alpha
                c.drawBitmap(box, src, dst, p)
            }
        }
        if (Stats.favorite(g)) {
            p.color = STAR
            p.alpha = alpha
            p.typeface = marker
            p.textSize = 42f
            c.drawText("*", left + 10f, top + 44f, p)
        }
    }

    /** The set's channel selector: a faceplate that stays put, a knob that turns, a highlight that doesn't. */
    private fun drawSpin(c: Canvas, left: Float, top: Float, w: Float, h: Float, alpha: Int) {
        dst.set(left, top, left + w, top + h)
        p.alpha = alpha
        c.drawBitmap(dialPlate, null, dst, p)
        c.save()
        c.rotate(dial, left + w / 2f, top + h * DIAL_Y)
        c.drawBitmap(dialKnob, null, dst, p)
        c.restore()
        c.drawBitmap(dialShine, null, dst, p)
    }

    private fun drawConsole(c: Canvas, it: Item.Console, left: Float, top: Float, w: Float, h: Float, alpha: Int) {
        dst.set(left, top + h * .10f, left + w, top + h)
        p.color = 0xFF1C1815.toInt()
        p.alpha = alpha
        c.drawRoundRect(dst, 8f, 8f, p)
        val bmp = art.get(Catalog.menuWheel[it.sys.db.lowercase()], 200)
        if (bmp != null) {
            val maxW = w - 40f
            val maxH = h * .50f
            val k = min(maxW / bmp.width, maxH / bmp.height)
            val bw = bmp.width * k
            val bh = bmp.height * k
            dst.set(left + (w - bw) / 2, top + h * .17f + (maxH - bh) / 2, left + (w + bw) / 2, top + h * .17f + (maxH + bh) / 2)
            src.set(0, 0, bmp.width, bmp.height)
            p.alpha = alpha
            c.drawBitmap(bmp, src, dst, p)
        } else {
            centered(c, it.sys.label, left + w / 2, top + h * .5f, 44f, TAPE, marker, alpha)
        }
        centered(c, gameCount(it.count), left + w / 2, top + h - 22f, 38f, PHOSPHOR, vcr, alpha)
    }

    private fun drawGenre(c: Canvas, it: Item.Genre, left: Float, top: Float, w: Float, h: Float, alpha: Int) {
        // a VHS tape standing on end, with a label across it
        dst.set(left, top + h * .06f, left + w, top + h)
        p.color = 0xFF131110.toInt()
        p.alpha = alpha
        c.drawRoundRect(dst, 6f, 6f, p)
        p.color = 0xFF050505.toInt()
        p.alpha = alpha
        dst.set(left + 24f, top + h * .62f, left + w - 24f, top + h - 18f)
        c.drawRoundRect(dst, 8f, 8f, p)
        p.color = TAPE
        p.alpha = alpha
        dst.set(left + 16f, top + h * .16f, left + w - 16f, top + h * .52f)
        c.drawRect(dst, p)
        p.color = GENRE_COLORS[abs(it.name.hashCode()) % GENRE_COLORS.size]
        p.alpha = alpha
        dst.set(left + 16f, top + h * .16f, left + w - 16f, top + h * .21f)
        c.drawRect(dst, p)
        val size = if (it.name.length > 10) 40f else 50f
        centered(c, it.name, left + w / 2, top + h * .40f, size, INK, marker, alpha)
        centered(c, "${it.count}", left + w / 2, top + h - 44f, 40f, PHOSPHOR, vcr, alpha)
    }

    private fun drawHero(c: Canvas) {
        val g = heroGame()
        val i = item
        val x = LEFT
        when {
            g != null -> {
                val wheel = art.get(g.wheel, 320)
                val baseline = 306f
                if (wheel != null) {
                    val k = min(760f / wheel.width, 210f / wheel.height)
                    val bw = wheel.width * k
                    val bh = wheel.height * k
                    dst.set(x, 256f - bh, x + bw, 256f)
                    src.set(0, 0, wheel.width, wheel.height)
                    p.alpha = 255
                    c.drawBitmap(wheel, src, dst, p)
                } else {
                    wrapped(c, g.title, x, 120f, 780f, 72f, 255, BONE)
                }
                val line = listOf(g.year, g.genre.orEmpty(), g.sys.label).filter { it.isNotBlank() }.joinToString("   ")
                label(c, line, x, baseline, 50f, AMBER, vcr)
                val last = Stats.last(g)
                if (last > 0L) {
                    val ago = DateUtils.getRelativeTimeSpanString(last, System.currentTimeMillis(), DateUtils.MINUTE_IN_MILLIS).toString()
                    val secs = Stats.seconds(g)
                    val played = if (secs >= 60) "   ${formatTime(secs)} on the clock" else ""
                    label(c, "Played $ago$played", x, baseline + 50f, 42f, BONE, vcr)
                }
                if (g.discs.size > 1) label(c, "Disc ${Stats.disc(g) + 1} of ${g.discs.size}", x, baseline + 96f, 42f, BONE, vcr)
            }
            i is Item.Console -> {
                val bmp = art.get(Catalog.menuWheel[i.sys.db.lowercase()], 320)
                if (bmp != null) {
                    val k = min(760f / bmp.width, 210f / bmp.height)
                    dst.set(x, 256f - bmp.height * k, x + bmp.width * k, 256f)
                    src.set(0, 0, bmp.width, bmp.height)
                    p.alpha = 255
                    c.drawBitmap(bmp, src, dst, p)
                } else {
                    label(c, i.sys.label, x, 230f, 92f, BONE, marker)
                }
                label(c, gameCount(i.count), x, 306f, 50f, AMBER, vcr)
            }
            i is Item.Genre -> {
                label(c, i.name, x, 230f, 110f, BONE, marker)
                label(c, gameCount(i.count), x, 306f, 50f, AMBER, vcr)
            }
            i is Item.Spin -> {
                label(c, "Play random", x, 230f, 110f, BONE, marker)
                label(c, gameCount(i.pool.size), x, 306f, 50f, AMBER, vcr)
            }
            i === Item.Search -> label(c, "Search", x, 230f, 110f, BONE, marker)
            i === Item.Stats -> {
                label(c, "Stats", x, 230f, 110f, BONE, marker)
                label(c, "${formatTime(Stats.total)} on the clock", x, 306f, 50f, AMBER, vcr)
            }
        }
        // what the buttons do right now
        val canPlay = g != null
        var bx = x
        val by = 458f
        if (canPlay) bx = button(c, "A", BTN_A, if (g != null && Launcher.hasResume(g, Stats.disc(g))) "Continue" else "Play", bx, by)
        else bx = button(c, "A", BTN_A, "Open", bx, by)
        bx = button(c, "Y", BTN_Y, "Random", bx, by)
        if (canPlay) bx = button(c, "X", BTN_X, "More", bx, by)
        if (pages.size > 1 || pick != null) button(c, "B", BTN_B, "Back", bx, by)
    }

    // ---- stats ------------------------------------------------------------------------------

    private fun drawStats(c: Canvas, l: Logbook) {
        val x = LEFT + 8f
        val right = STATS_R - 26f
        p.style = Paint.Style.FILL
        p.color = 0xC8100C0A.toInt()
        dst.set(LEFT - 14f, 40f, STATS_R, 606f)
        c.drawRoundRect(dst, 14f, 14f, p)

        val big = formatTime(l.total)
        label(c, big, x, 150f, 112f, BONE, marker)
        label(c, "on the clock", x + measure(big, 112f, marker) + 24f, 150f, 50f, AMBER, vcr)

        val mid = (x + right) / 2f
        figure(c, "This week", formatTime(l.week), x, mid - 30f, 214f)
        figure(c, "Games played", "${l.tried} of ${l.library}", mid + 30f, right, 214f)
        figure(c, "Sessions", "${l.sessions}", x, mid - 30f, 264f)
        figure(c, "Day streak", if (l.bestStreak > l.streak) "${l.streak} (best ${l.bestStreak})" else "${l.streak}", mid + 30f, right, 264f)
        val long = l.longest
        val title = l.longestTitle
        val longText = when {
            long == null -> "-"
            title == null -> formatTime(long.secs)
            else -> "${formatTime(long.secs)}  $title"
        }
        figure(c, "Longest", clip(longText, right - x - 170f, 42f), x, right, 314f)

        // where the time went
        val top = (l.systems.firstOrNull()?.second ?: 1L).toFloat()
        l.systems.forEachIndexed { k, (sys, secs) ->
            val y = 372f + k * 42f
            label(c, sys.label, x, y, 38f, BONE, vcr)
            val time = formatTime(secs)
            label(c, time, right - measure(time, 38f, vcr), y, 38f, BONE, vcr)
            val barL = x + 330f
            val barR = right - 120f
            p.style = Paint.Style.FILL
            p.color = AMBER
            p.alpha = 220
            dst.set(barL, y - 24f, barL + max(4f, (barR - barL) * (secs / top)), y - 2f)
            c.drawRect(dst, p)
            p.alpha = 255
        }

        // the game on the shelf right now, and what the buttons do
        val g = heroGame()
        if (g != null) {
            val secs = Stats.seconds(g)
            val ago = Stats.last(g).takeIf { it > 0L }?.let {
                DateUtils.getRelativeTimeSpanString(it, System.currentTimeMillis(), DateUtils.MINUTE_IN_MILLIS, DateUtils.FORMAT_ABBREV_ALL or DateUtils.FORMAT_NO_YEAR).toString()
            }
            val plays = Stats.plays(g)
            val line = listOfNotNull(if (secs > 0) formatTime(secs) else null, "$plays ${if (plays == 1) "play" else "plays"}", ago).joinToString("   ")
            label(c, line, right - measure(line, 40f, vcr), 574f, 40f, AMBER, vcr)
            label(c, clip(g.title, right - x - measure(line, 40f, vcr) - 30f, 40f, marker), x, 574f, 40f, BONE, marker)
        }
        var bx = LEFT
        val by = 650f
        if (g != null) bx = button(c, "A", BTN_A, if (Launcher.hasResume(g, Stats.disc(g))) "Continue" else "Play", bx, by)
        else if (item is Item.Spin) bx = button(c, "A", BTN_A, "Random", bx, by)
        if (g != null) bx = button(c, "X", BTN_X, "More", bx, by)
        button(c, "B", BTN_B, "Back", bx, by)

        drawChart(c, l)
    }

    private fun figure(c: Canvas, name: String, value: String, x: Float, r: Float, y: Float) {
        label(c, name, x, y, 42f, AMBER, vcr)
        label(c, value, r - measure(value, 42f, vcr), y, 42f, BONE, vcr)
    }

    /** The last month, on the set itself. */
    private fun drawChart(c: Canvas, l: Logbook) {
        c.save()
        c.clipPath(tube)
        c.concat(osdMatrix)
        p.style = Paint.Style.FILL
        p.color = 0xE8040A06.toInt()
        c.drawRect(0f, 0f, 640f, 480f, p)
        label(c, "LAST 30 DAYS", 40f, 76f, 50f, PHOSPHOR, vcr)
        val month = formatTime(l.month).uppercase()
        label(c, month, 600f - measure(month, 50f, vcr), 76f, 50f, PHOSPHOR, vcr)
        val floor = 388f
        val height = 262f
        val peak = (l.days.maxOrNull() ?: 0L).coerceAtLeast(1L).toFloat()
        val w = 560f / Logbook.DAYS
        // the tallest bar says what it's worth, so the rest can be read off it
        if (l.month > 0L) {
            val tall = l.days.indices.maxByOrNull { l.days[it] } ?: 0
            val peakText = formatTime(l.days[tall]).uppercase()
            val tw = measure(peakText, 34f, vcr)
            val px = (40f + (tall + .5f) * w - tw / 2f).coerceIn(40f, 600f - tw)
            label(c, peakText, px, floor - height - 6f, 34f, PHOSPHOR, vcr)
        }
        for (k in l.days.indices) {
            val secs = l.days[k]
            val bx = 40f + k * w
            val barH = if (secs > 0) max(5f, height * (secs / peak)) else 2f
            p.color = PHOSPHOR
            p.alpha = if (secs == 0L) 70 else if (k == l.days.size - 1) 255 else 190
            dst.set(bx + 2f, floor - barH, bx + w - 2f, floor)
            c.drawRect(dst, p)
        }
        p.alpha = 255
        val from = DateUtils.formatDateTime(context, System.currentTimeMillis() - (Logbook.DAYS - 1) * 86400000L, DateUtils.FORMAT_SHOW_DATE or DateUtils.FORMAT_NO_YEAR or DateUtils.FORMAT_ABBREV_MONTH).uppercase()
        label(c, from, 40f, 436f, 42f, PHOSPHOR, vcr)
        label(c, "TODAY", 600f - measure("TODAY", 42f, vcr), 436f, 42f, PHOSPHOR, vcr)
        c.restore()
    }

    /** Cut to fit, with a dot dot dot. */
    private fun clip(t: String, w: Float, size: Float, face: Typeface = vcr): String {
        if (measure(t, size, face) <= w) return t
        var n = t.length
        while (n > 1 && measure(t.take(n) + "...", size, face) > w) n--
        return t.take(n).trimEnd() + "..."
    }

    private fun button(c: Canvas, letter: String, color: Int, text: String, x: Float, y: Float): Float {
        p.color = color
        p.style = Paint.Style.FILL
        c.drawCircle(x + 22f, y - 14f, 23f, p)
        centered(c, letter, x + 22f, y - 1f, 38f, Color.WHITE, vcr, 255)
        label(c, text, x + 54f, y, 42f, BONE, vcr)
        return x + 54f + measure(text, 42f, vcr) + 46f
    }

    private fun formatTime(secs: Long): String {
        val h = secs / 3600
        val m = (secs % 3600) / 60
        return if (h > 0) "${h}h ${m}m" else "${m}m"
    }

    private fun drawOsd(c: Canvas) {
        val now = SystemClock.uptimeMillis()
        if (now > osdUntil) return
        val a = (min(1f, (osdUntil - now) / 300f) * 255).toInt()
        c.save()
        c.concat(osdMatrix)
        label(c, osd, 42f, 76f, 68f, PHOSPHOR, vcr, a)
        c.restore()
    }

    private fun drawTapeNote(c: Canvas) {
        val g = heroGame() ?: return
        val nx = Geo.screen[6] - 4f
        val ny = Geo.screen[7] + 26f
        c.save()
        c.rotate(-1.5f, nx, ny)
        val text = g.sys.leave
        val w = measure(text, 28f, marker) + 30f
        p.color = TAPE
        p.alpha = 242
        p.style = Paint.Style.FILL
        dst.set(nx, ny, nx + w, ny + 40f)
        c.drawRect(dst, p)
        label(c, text, nx + 15f, ny + 30f, 28f, INK, marker)
        c.restore()
    }

    private fun drawMenu(c: Canvas, m: Menu) {
        p.color = 0xB8000000.toInt()
        p.style = Paint.Style.FILL
        c.drawRect(0f, 0f, 1920f, 1080f, p)
        val w = 720f
        val h = 96f + m.entries.size * 76f
        val x = (1920f - w) / 2
        val y = (1080f - h) / 2
        p.color = TAPE
        dst.set(x, y, x + w, y + h)
        c.drawRect(dst, p)
        centeredFit(c, m.game.title, 960f, y + 62f, 44f, w - 60f, INK, marker)
        m.entries.forEachIndexed { k, e ->
            val ey = y + 96f + k * 76f
            if (k == m.index) {
                p.color = NEON
                dst.set(x + 24f, ey, x + w - 24f, ey + 66f)
                c.drawRect(dst, p)
            }
            centered(c, e.first, 960f, ey + 49f, 46f, if (k == m.index) Color.WHITE else INK, marker, 255)
        }
    }

    // ---- text and tape ----------------------------------------------------------------------

    private fun measure(t: String, size: Float, face: Typeface): Float {
        p.typeface = face
        p.textSize = size
        return p.measureText(t)
    }

    private fun label(c: Canvas, t: String, x: Float, y: Float, size: Float, color: Int, face: Typeface, alpha: Int = 255) {
        p.typeface = face
        p.textSize = size
        p.color = color
        p.alpha = alpha
        p.style = Paint.Style.FILL
        c.drawText(t, x, y, p)
    }

    private fun centered(c: Canvas, t: String, cx: Float, y: Float, size: Float, color: Int, face: Typeface, alpha: Int) {
        label(c, t, cx - measure(t, size, face) / 2f, y, size, color, face, alpha)
    }

    private fun centeredFit(c: Canvas, t: String, cx: Float, y: Float, size: Float, maxW: Float, color: Int, face: Typeface) {
        val w = measure(t, size, face)
        val sz = if (w > maxW) size * maxW / w else size
        centered(c, t, cx, y, sz, color, face, 255)
    }

    private fun wrapped(c: Canvas, t: String, x: Float, y: Float, w: Float, size: Float, alpha: Int, color: Int = INK) {
        var line = ""
        var yy = y
        for (word in t.split(' ')) {
            val next = if (line.isEmpty()) word else "$line $word"
            if (measure(next, size, marker) > w && line.isNotEmpty()) {
                label(c, line, x, yy, size, color, marker, alpha)
                yy += size * 1.15f
                line = word
            } else {
                line = next
            }
        }
        label(c, line, x, yy, size, color, marker, alpha)
    }

    private fun tape(c: Canvas, t: String, x: Float, y: Float, alpha: Int) {
        val w = measure(t, 34f, marker) + 36f
        c.save()
        c.rotate(-.8f, x, y + 22f)
        p.color = TAPE
        p.alpha = alpha
        p.style = Paint.Style.FILL
        dst.set(x, y, x + w, y + 46f)
        c.drawRect(dst, p)
        label(c, t, x + 18f, y + 35f, 34f, INK, marker, alpha)
        c.restore()
    }

    companion object {
        private val CODE = intArrayOf(
            KeyEvent.KEYCODE_DPAD_UP, KeyEvent.KEYCODE_DPAD_UP, KeyEvent.KEYCODE_DPAD_DOWN, KeyEvent.KEYCODE_DPAD_DOWN,
            KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_DPAD_RIGHT, KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_DPAD_RIGHT,
        )
        private val SHELVES = listOf(PICK to "Put on the home screen", SHELF to "Put on the shelf", BACK to "Send to the back room")
        private const val TILE_H = 262f
        private const val DIAL_Y = .405f
        private const val KEY = 84f
        private const val GAP = 26f
        private const val LEFT = 70f
        private const val STATS_R = 1124f
        private const val ROWS_Y = 684f
        private const val ROW_PITCH = 356f

        private const val BONE = 0xFFEDE3CC.toInt()
        private const val AMBER = 0xFFFFB45A.toInt()
        private const val PHOSPHOR = 0xFF7DFF9E.toInt()
        private const val TAPE = 0xFFE3D5AE.toInt()
        private const val INK = 0xFF1B1714.toInt()
        private const val NEON = 0xFFFF2E93.toInt()
        private const val STAR = 0xFFFFD23C.toInt()
        private const val BTN_A = 0xFF2E9E4F.toInt()
        private const val BTN_B = 0xFFC8322B.toInt()
        private const val BTN_X = 0xFF2B62C8.toInt()
        private const val BTN_Y = 0xFFD9A514.toInt()
        private val GENRE_COLORS = intArrayOf(0xFFFF2E93.toInt(), 0xFF19C4C4.toInt(), 0xFFFFB45A.toInt(), 0xFF7A5CFF.toInt(), 0xFF53D769.toInt())
    }
}
