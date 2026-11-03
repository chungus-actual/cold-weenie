package io.github.chungus_actual.coldweenie

import android.view.InputDevice
import java.util.Calendar
import kotlin.random.Random

sealed class Item {
    class Play(val game: Game, val resume: Boolean = false) : Item()
    class Spin(val pool: List<Game>) : Item()
    object Search : Item()
    object Stats : Item()
    class Console(val sys: Sys, val count: Int) : Item()
    class Genre(val name: String, val count: Int) : Item()
}

fun gameCount(n: Int) = if (n == 1) "1 game" else "$n games"

class Row(val title: String, val items: List<Item>) {
    var index = 0
    var scroll = 0f
    var scrollTo = 0f
}

class Page(val rows: List<Row>, val pool: List<Game>, val log: Logbook? = null) {
    var rowIndex = 0
    var rowScroll = 0f
}

/** Controllers switched on right now. The Harmony hub calls itself a joystick too, so only a real gamepad counts. */
object Pads {
    fun count() = InputDevice.getDeviceIds().count { id ->
        InputDevice.getDevice(id)?.let { !it.isVirtual && it.sources and InputDevice.SOURCE_GAMEPAD == InputDevice.SOURCE_GAMEPAD } ?: false
    }
}

/** The shelves: what is on them, in what order, and why. */
object Rows {
    /** Somebody knew the code. Lasts until the app closes. */
    var thirtyLives = false

    private val COUCH = setOf("Fighting", "Party", "Racing", "Sports", "Beat 'em ups")

    /** Changes every six hours, so the same games aren't always staring at you. */
    private fun todaySeed(): Int {
        val c = Calendar.getInstance()
        return c.get(Calendar.YEAR) * 1000 + c.get(Calendar.DAY_OF_YEAR) * 4 + c.get(Calendar.HOUR_OF_DAY) / 6
    }

    private fun recents(pool: List<Game>) = pool.filter { Stats.plays(it) > 0 }.sortedByDescending { Stats.last(it) }

    private fun keepPlaying(pool: List<Game>): Row? {
        val r = recents(pool).take(14)
        if (r.isEmpty()) return null
        return Row("Keep playing", r.map { Item.Play(it, resume = true) })
    }

    private fun Row.nonEmpty() = takeIf { items.isNotEmpty() }

    fun home(): Page {
        val all = Catalog.games
        val picks = all.filter { it.pick }
        val rnd = Random(todaySeed())
        val played = recents(all)
        val rows = ArrayList<Row>()
        if (thirtyLives) {
            val theirs = all.filter { it.listed && it.maker.contains("Konami", ignoreCase = true) }
            rows += Row("30 lives", listOf<Item>(Item.Spin(theirs)) + theirs.shuffled(rnd).take(40).map { Item.Play(it) })
        }
        // a second controller just came on: that's what tonight is about
        val pads = Pads.count()
        if (pads >= 2) {
            val together = picks.filter { it.players >= pads && it.onOneTv }
            val name = if (pads == 2) "Two players" else "$pads players"
            rows += Row(name, listOf<Item>(Item.Spin(together)) + together.shuffled(rnd).take(24).map { Item.Play(it) })
        }
        keepPlaying(all)?.let(rows::add)

        // Tonight: games you haven't touched lately, leaning toward what you do play, a few per system
        val genreWeight = played.mapNotNull { it.genre }.groupingBy { it }.eachCount()
        val sysWeight = played.groupingBy { it.sys.id }.eachCount()
        val maxG = (genreWeight.values.maxOrNull() ?: 1).toFloat()
        val maxS = (sysWeight.values.maxOrNull() ?: 1).toFloat()
        val weekAgo = System.currentTimeMillis() - 14L * 86400000L
        val ranked = picks.filter { Stats.last(it) < weekAgo }
            .map { g ->
                val score = rnd.nextFloat() +
                    (genreWeight[g.genre] ?: 0) / maxG * .7f +
                    (sysWeight[g.sys.id] ?: 0) / maxS * .35f +
                    (if (Stats.favorite(g)) .4f else 0f)
                g to score
            }.sortedByDescending { it.second }
        val perSys = HashMap<String, Int>()
        val tonight = ArrayList<Game>()
        for ((g, _) in ranked) {
            val n = perSys[g.sys.id] ?: 0
            if (n >= 3) continue
            perSys[g.sys.id] = n + 1
            tonight += g
            if (tonight.size >= 18) break
        }
        // first, whatever else turned up today: this is the row with the way into everything
        rows.add(0, Row(if (all.isEmpty()) "No games in ${Catalog.ROOT.name}/Roms yet" else "Tonight", listOf<Item>(Item.Spin(picks), Item.Search, Item.Stats) + tonight.map { Item.Play(it) }))

        played.firstOrNull()?.let { last ->
            val like = picks.filter { it.genre == last.genre && it !== last }
                .sortedByDescending { (if (it.sys === last.sys) .4f else 0f) + rnd.nextFloat() }.take(14)
            if (like.isNotEmpty()) rows += Row("Because you played ${last.title}", like.map { Item.Play(it) })
        }

        val favs = all.filter { Stats.favorite(it) }
        if (favs.isNotEmpty()) rows += Row("Favorites", favs.map { Item.Play(it) })

        rows += Row("Couch night", picks.filter { it.genre in COUCH && it.players != 1 && it.onOneTv }.shuffled(rnd).take(18).map { Item.Play(it) })

        rows += Row(
            "Consoles",
            SYSTEMS.mapNotNull { s -> Catalog.bySys[s.id]?.count { it.listed }?.takeIf { it > 0 }?.let { Item.Console(s, it) } },
        )
        rows += Row(
            "Genres",
            Catalog.byGenre.entries.sortedByDescending { it.value.size }.map { Item.Genre(it.key, it.value.size) },
        )
        rows += Row("Never touched", picks.filter { Stats.plays(it) == 0 }.shuffled(rnd).take(24).map { Item.Play(it) }).nonEmpty().let { it ?: Row("Never touched", emptyList()) }
        val backRoom = all.filter { !it.listed }
        if (backRoom.isNotEmpty()) rows += Row("Back room", backRoom.map { Item.Play(it) })
        return Page(rows.filter { it.items.isNotEmpty() }, picks)
    }

    fun stats(): Page {
        val all = Catalog.games
        val rows = ArrayList<Row>()
        val most = all.filter { Stats.seconds(it) > 0 }.sortedByDescending { Stats.seconds(it) }
        if (most.isNotEmpty()) rows += Row("Most played", most.take(40).map { Item.Play(it) })
        val cutoff = Stats.dayOf(System.currentTimeMillis()) - Logbook.DAYS
        val lately = HashMap<String, Long>()
        for (s in Stats.sessions) if (Stats.dayOf(s.at) > cutoff) lately[s.id] = (lately[s.id] ?: 0L) + s.secs
        val recent = all.filter { it.id in lately }.sortedByDescending { lately[it.id] }
        if (recent.isNotEmpty()) rows += Row("Most played lately", recent.take(40).map { Item.Play(it) })
        if (rows.isEmpty()) rows += Row("Nothing on the clock yet", listOf(Item.Spin(all.filter { it.pick })))
        return Page(rows, most, Logbook(all))
    }

    fun search(box: SearchBox): Page {
        val r = box.results
        return Page(listOf(Row(if (box.query.isEmpty()) "Everything" else "${r.size} found", r.take(240).map { Item.Play(it) })), r)
    }

    fun console(sys: Sys): Page {
        val games = Catalog.bySys[sys.id].orEmpty()
        val rows = ArrayList<Row>()
        keepPlaying(games)?.let(rows::add)
        val listed = games.filter { it.listed }
        val genres = listed.filter { it.genre != null }.groupBy { it.genre!! }.entries.sortedByDescending { it.value.size }
        rows += Row("All of them", listOf<Item>(Item.Spin(listed)) + listed.map { Item.Play(it) })
        genres.forEach { (g, list) -> rows += Row(g, list.map { Item.Play(it) }) }
        val extra = games.filter { !it.listed }
        if (extra.isNotEmpty()) rows += Row("Back room", extra.map { Item.Play(it) })
        return Page(rows, listed)
    }

    fun genre(name: String): Page {
        val games = Catalog.byGenre[name].orEmpty()
        val rows = ArrayList<Row>()
        val rnd = Random(todaySeed())
        rows += Row(name, listOf<Item>(Item.Spin(games)) + games.shuffled(rnd).take(20).map { Item.Play(it) })
        SYSTEMS.reversed().forEach { s ->
            val list = games.filter { it.sys === s }
            if (list.isNotEmpty()) rows += Row(s.label, list.map { Item.Play(it) })
        }
        return Page(rows, games)
    }
}
