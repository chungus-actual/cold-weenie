package io.github.chungus_actual.coldweenie

import java.io.File
import java.util.TimeZone
import org.json.JSONObject

class Session(val id: String, val at: Long, val secs: Long)

/** What has been played, kept outside the app so a reinstall loses nothing. */
object Stats {
    val dir = File("/storage/emulated/0/${BuildConfig.DATA_DIR}").apply { mkdirs() }
    private val file = File(dir, "stats.json")
    private val log = File(dir, "sessions.jsonl")
    private val running = File(dir, "running.json")
    private val root: JSONObject = runCatching { JSONObject(file.readText()) }.getOrDefault(JSONObject())

    /** Every session, oldest first. */
    val sessions = ArrayList<Session>().apply {
        runCatching {
            log.forEachLine { line ->
                runCatching {
                    val o = JSONObject(line)
                    add(Session(o.getString("g"), o.getLong("t"), o.getLong("s")))
                }
            }
        }
    }

    private fun rec(id: String): JSONObject = root.optJSONObject(id) ?: JSONObject().also { root.put(id, it) }

    fun last(g: Game) = root.optJSONObject(g.id)?.optLong("last") ?: 0L
    fun plays(g: Game) = root.optJSONObject(g.id)?.optInt("n") ?: 0
    fun seconds(g: Game) = root.optJSONObject(g.id)?.optLong("secs") ?: 0L
    fun favorite(g: Game) = root.optJSONObject(g.id)?.optBoolean("fav") ?: false
    fun disc(g: Game) = (root.optJSONObject(g.id)?.optInt("disc") ?: 0).coerceIn(0, g.discs.size - 1)

    /** All time, including anything from games that have since left the library. */
    var total = root.keys().asSequence().sumOf { root.optJSONObject(it)?.optLong("secs") ?: 0L }
        private set

    /** On disk straight away: the launcher may well be gone by the time the game ends. */
    fun started(g: Game, disc: Int, pkg: String, uptime: Long) {
        rec(g.id).put("n", plays(g) + 1).put("last", System.currentTimeMillis()).put("disc", disc)
        save()
        runCatching {
            running.writeText(JSONObject().put("g", g.id).put("t", System.currentTimeMillis()).put("p", pkg).put("u", uptime).toString())
        }
    }

    /** The session still open, if a game was started and nobody has counted it yet. */
    fun open(): JSONObject? = runCatching { JSONObject(running.readText()) }.getOrNull()

    fun finished(id: String, at: Long, secs: Long) {
        running.delete()
        if (secs < MIN_SESSION) return
        rec(id).put("secs", (root.optJSONObject(id)?.optLong("secs") ?: 0L) + secs)
        total += secs
        save()
        sessions += Session(id, at, secs)
        runCatching { log.appendText(JSONObject().put("g", id).put("t", at).put("s", secs).toString() + "\n") }
    }

    fun shelf(id: String): String? = root.optJSONObject(id)?.optString("shelf")?.ifEmpty { null }

    fun setShelf(g: Game, shelf: String) {
        rec(g.id).put("shelf", shelf)
        save()
    }

    fun toggleFavorite(g: Game) {
        rec(g.id).put("fav", !favorite(g))
        save()
    }

    private fun save() {
        val tmp = File(dir, "stats.json.tmp")
        runCatching {
            tmp.writeText(root.toString())
            tmp.renameTo(file)
        }
    }

    /** Local calendar day, as a plain count. */
    fun dayOf(t: Long) = (t + TimeZone.getDefault().getOffset(t)) / 86400000L

    /** Shorter than this is a crash or a change of mind, not playing. */
    private const val MIN_SESSION = 20L
}

/** The numbers on the stats page, worked out once when it opens. */
class Logbook(games: List<Game>) {
    val total = Stats.total
    /** Oldest first; the last one is today. */
    val days = LongArray(DAYS)
    val sessions = Stats.sessions.size
    val longest: Session? = Stats.sessions.maxByOrNull { it.secs }
    val longestTitle: String?
    val tried = games.count { Stats.plays(it) > 0 }
    val library = games.size
    val systems: List<Pair<Sys, Long>>
    val streak: Int
    val bestStreak: Int
    val week get() = days.takeLast(7).sum()
    val month get() = days.sum()
    val today = Stats.dayOf(System.currentTimeMillis())

    init {
        val byId = games.associateBy { it.id }
        longestTitle = longest?.let { byId[it.id]?.title }
        val played = HashSet<Long>()
        for (s in Stats.sessions) {
            val d = Stats.dayOf(s.at)
            played += d
            val back = (today - d).toInt()
            if (back in 0 until DAYS) days[DAYS - 1 - back] += s.secs
        }
        systems = games.groupBy { it.sys }.map { (sys, list) -> sys to list.sumOf { Stats.seconds(it) } }
            .filter { it.second > 0 }.sortedByDescending { it.second }.take(4)
        var best = 0
        var run = 0
        var prev = Long.MIN_VALUE
        for (d in played.sorted()) {
            run = if (d == prev + 1) run + 1 else 1
            best = maxOf(best, run)
            prev = d
        }
        bestStreak = best
        // still alive today if you played yesterday
        var from = if (today in played) today else today - 1
        var now = 0
        while (from in played) {
            now++
            from--
        }
        streak = now
    }

    companion object {
        const val DAYS = 30
    }
}
