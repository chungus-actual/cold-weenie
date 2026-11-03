package io.github.chungus_actual.coldweenie

import kotlin.math.abs

/**
 * Find a game by typing a few letters. Words match by prefix, in any order. After each letter the keys
 * rearrange: that letter sits in the middle with the letters most likely to come next right around it,
 * and letters that couldn't lead to any game aren't there at all.
 */
class SearchBox(games: List<Game>) {
    class Cell(val col: Int, val row: Int, val ch: Char, val strength: Float, val hub: Boolean = false)

    private class Entry(val game: Game, val words: List<String>)

    private val entries = games.map { Entry(it, words(it.title)) }
    var query = ""
        private set
    var results: List<Game> = emptyList()
        private set
    var cells: List<Cell> = emptyList()
        private set
    /** Index into cells. */
    var focus = 0

    init {
        update()
    }

    fun type(c: Char) {
        val ch = c.lowercaseChar()
        if (ch == ' ' && (query.isEmpty() || query.endsWith(' '))) return
        query += ch
        update()
    }

    fun erase() {
        if (query.isEmpty()) return
        query = query.dropLast(1)
        update()
    }

    fun set(text: String) {
        query = words(text).joinToString(" ")
        update()
    }

    fun pick() {
        val c = cells.getOrNull(focus) ?: return
        if (c.hub && c.strength <= 0f) return
        type(c.ch)
    }

    /** Moves focus; false when there's nothing further that way. */
    fun move(dc: Int, dr: Int): Boolean {
        val from = cells.getOrNull(focus) ?: return false
        var best = -1
        var bestScore = Int.MAX_VALUE
        cells.forEachIndexed { i, c ->
            val x = c.col - from.col
            val y = c.row - from.row
            val along = x * dc + y * dr
            if (along > 0) {
                val across = abs(x * dr) + abs(y * dc)
                val score = along * 3 + across * 4
                if (score < bestScore) {
                    bestScore = score
                    best = i
                }
            }
        }
        if (best < 0) return false
        focus = best
        return true
    }

    private fun tokens() = query.split(' ').filter { it.isNotEmpty() }

    private fun update() {
        val toks = tokens()
        results = if (toks.isEmpty()) {
            entries.filter { it.game.listed }.map { it.game }
        } else {
            val all = entries.filter { e -> toks.all { t -> e.words.any { it.startsWith(t) } } }
            (all.ifEmpty { entries.filter { e -> toks.any { t -> e.words.any { it.startsWith(t) } } } })
                .sortedWith(
                    compareByDescending<Entry> { e -> toks.count { t -> e.words.any { it.startsWith(t) } } }
                        .thenByDescending { it.game.listed }
                        .thenByDescending { e -> e.words.firstOrNull()?.startsWith(toks[0]) == true }
                        .thenBy { it.game.title.length },
                ).map { it.game }
        }
        layOut()
    }

    /** What could come next, likeliest first: titles with art count for more, and so do first words. */
    private fun nextLetters(): Map<Char, Float> {
        val prior = if (query.endsWith(' ')) tokens() else tokens().dropLast(1)
        val tail = if (query.endsWith(' ')) "" else tokens().lastOrNull().orEmpty()
        val out = HashMap<Char, Float>()
        for (e in entries) {
            if (!prior.all { t -> e.words.any { it.startsWith(t) } }) continue
            e.words.forEachIndexed { i, w ->
                if (tail.isEmpty() || w.startsWith(tail)) {
                    val weight = (if (e.game.listed) 3f else 1f) * (if (i == 0) 2f else 1f)
                    if (w.length > tail.length) {
                        val c = w[tail.length]
                        out[c] = (out[c] ?: 0f) + weight
                    } else if (tail.isNotEmpty() && e.words.size > 1) {
                        out[' '] = (out[' '] ?: 0f) + weight
                    }
                }
            }
        }
        // no game leads there, so the keys wouldn't offer it, but you can always spell it
        val typed = query.filter { it.isLetter() }.lowercase()
        if (typed.length in 3..5 && "hotdog".startsWith(typed)) {
            out["hotdog"[typed.length]] = out.values.maxOrNull() ?: 1f
        }
        return out
    }

    private fun layOut() {
        val next = nextLetters()
        val top = next.values.maxOrNull() ?: 1f
        fun strength(c: Char) = ((next[c] ?: 0f) / top).coerceIn(0f, 1f)
        val out = ArrayList<Cell>()
        if (query.isEmpty()) {
            // nothing typed yet: the alphabet, where you expect it
            var n = 0
            for (c in "abcdefghijklmnopqrstuvwxyz0123456789") {
                if (c !in next) continue
                if (n >= COLS * ROWS) break
                out += Cell(n % COLS, n / COLS, c, strength(c))
                n++
            }
            focus = out.indexOfFirst { it.ch == 'm' }.coerceAtLeast(0)
        } else {
            val last = query.last()
            out += Cell(CENTER_COL, CENTER_ROW, last, if (last != ' ') strength(last) else 0f, hub = true)
            val around = next.entries.filter { it.key != last }.sortedByDescending { it.value }
            around.take(SPOTS.size).forEachIndexed { i, e ->
                out += Cell(SPOTS[i].first, SPOTS[i].second, e.key, strength(e.key))
            }
            focus = 0
        }
        cells = out
    }

    companion object {
        const val COLS = 7
        const val ROWS = 5
        private const val CENTER_COL = 3
        private const val CENTER_ROW = 2

        /** Every key but the middle one, nearest first: straight up, down, left and right before the corners. */
        private val SPOTS = (0 until ROWS).flatMap { r -> (0 until COLS).map { c -> c to r } }
            .filter { it != CENTER_COL to CENTER_ROW }
            .sortedWith(compareBy({ abs(it.first - CENTER_COL) + abs(it.second - CENTER_ROW) }, { abs(it.second - CENTER_ROW) }))

        private val ROMAN = mapOf("ii" to "2", "iii" to "3", "iv" to "4", "vi" to "6", "vii" to "7", "viii" to "8", "ix" to "9")

        fun words(s: String): List<String> {
            val base = s.lowercase().replace("'", "").replace(Regex("[^a-z0-9]+"), " ").trim().split(' ').filter { it.isNotEmpty() }
            // what you'd say out loud finds what's on the box, either way around
            return base + base.mapNotNull { w -> ROMAN[w] ?: ROMAN.entries.firstOrNull { it.value == w }?.key }
        }
    }
}
