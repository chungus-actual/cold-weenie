package io.github.chungus_actual.coldweenie

import java.io.File
import android.graphics.BitmapFactory
import org.json.JSONArray
import org.json.JSONObject

/** How a system's games start. */
sealed class Launch {
    class Core(val core: String) : Launch()
    object Flycast : Launch()
    object Dolphin : Launch()
    object Ppsspp : Launch()
}

class Sys(
    val id: String,
    val label: String,
    val db: String,
    val roms: String,
    val media: String,
    val exts: Set<String>,
    val channel: Int,
    val launch: Launch,
    /** The tape note on the TV: how you get back here from a game. */
    val leave: String,
)

private const val START_SELECT = "Start + Select to leave"

val SYSTEMS = listOf(
    Sys("arcade", "Arcade", "MAME", "MAME", "Mame", setOf("zip"), 1, Launch.Core("mame2010"), START_SELECT),
    Sys("nes", "NES", "Nintendo Entertainment System", "Nintendo Entertainment System", "Nintendo Entertainment System", setOf("nes", "zip"), 3, Launch.Core("nestopia"), START_SELECT),
    Sys("sms", "Master System", "Sega Master System", "Sega Master System", "Sega Master System", setOf("sms", "zip"), 4, Launch.Core("genesis_plus_gx"), START_SELECT),
    Sys("gb", "Game Boy", "Nintendo Game Boy", "Nintendo Game Boy", "Nintendo Game Boy", setOf("gb"), 5, Launch.Core("gambatte"), START_SELECT),
    Sys("genesis", "Genesis", "Sega Genesis", "Sega Genesis", "Sega Genesis", setOf("md", "gen", "bin"), 6, Launch.Core("genesis_plus_gx"), START_SELECT),
    Sys("lynx", "Lynx", "Atari Lynx", "Atari Lynx", "Atari Lynx", setOf("lnx"), 7, Launch.Core("handy"), START_SELECT),
    Sys("gg", "Game Gear", "Sega Game Gear", "Sega Game Gear", "Sega Game Gear", setOf("gg"), 8, Launch.Core("genesis_plus_gx"), START_SELECT),
    Sys("snes", "Super NES", "Super Nintendo Entertainment System", "Super Nintendo Entertainment System", "Super Nintendo Entertainment System", setOf("sfc", "smc"), 9, Launch.Core("snes9x"), START_SELECT),
    Sys("saturn", "Saturn", "Sega Saturn", "Sega Saturn", "Sega Saturn", setOf("cue"), 11, Launch.Core("yabasanshiro"), START_SELECT),
    Sys("ps1", "PlayStation", "Sony Playstation", "Sony Playstation", "Sony PlayStation", setOf("pbp", "cue", "chd"), 12, Launch.Core("pcsx_rearmed"), START_SELECT),
    Sys("n64", "Nintendo 64", "Nintendo 64", "Nintendo 64", "Nintendo 64", setOf("n64", "z64", "v64"), 13, Launch.Core("mupen64plus_next_gles3"), START_SELECT),
    Sys("gbc", "Game Boy Color", "Nintendo Game Boy Color", "Nintendo Game Boy Color", "Nintendo Game Boy Color", setOf("gbc"), 14, Launch.Core("gambatte"), START_SELECT),
    Sys("dc", "Dreamcast", "Sega Dreamcast", "Sega Dreamcast", "Sega Dreamcast", setOf("chd", "cdi", "gdi"), 15, Launch.Flycast, "Back, Close Game, then Home"),
    Sys("gba", "Game Boy Advance", "Nintendo Game Boy Advance", "Nintendo Game Boy Advance", "Nintendo Game Boy Advance", setOf("gba"), 16, Launch.Core("mgba"), START_SELECT),
    Sys("gc", "GameCube", "Nintendo GameCube", "Nintendo GameCube", "Nintendo GameCube", setOf("gcz", "rvz", "iso"), 17, Launch.Dolphin, "Back, Exit, then Home"),
    Sys("psp", "PSP", "Sony PSP", "Sony PSP", "Sony PSP", setOf("cso", "iso", "chd"), 18, Launch.Ppsspp, "Back, Exit to menu, then Home"),
)

/** Which shelf a game earned. On the home screen and in Play Random; on its console and genre pages; in the back room. */
const val PICK = "pick"
const val SHELF = "shelf"
const val BACK = "back"
private val HANDHELDS = setOf("gb", "gbc", "gba", "gg", "lynx", "psp")

class Game(
    val sys: Sys,
    val base: String,
    val title: String,
    val year: String,
    val maker: String,
    val genre: String?,
    val discs: List<File>,
    val box: String?,
    val cart: String?,
    val wheel: String?,
    val video: String?,
    val earned: String,
    /** The core this one game needs, when it isn't the system's own: arcade romsets each fit one MAME. */
    val core: String? = null,
    /** Most players at once, 0 when nobody knows. */
    val players: Int = 0,
) {
    val id = "${sys.id}/$base"
    /** Moved by hand from the More menu, else what the catalogue says. */
    val shelf get() = Stats.shelf(id) ?: earned
    val listed get() = shelf != BACK
    val pick get() = shelf == PICK
    /** Handhelds count their link cable as a second player, which is no use on one TV. */
    val onOneTv get() = sys.id !in HANDHELDS
    var aspect = 0.72f
    val rom get() = discs[0]
}

object Catalog {
    /** The library: a folder holding Roms, on a drive plugged into the box if one has it, else internal storage. */
    val ROOT: File by lazy {
        val names = BuildConfig.LIBRARY.split(',')
        val places = File("/storage").listFiles().orEmpty().filter { it.name != "emulated" && it.name != "self" } + File("/storage/emulated/0")
        names.flatMap { name -> places.map { File(it, name) } }.firstOrNull { File(it, "Roms").isDirectory }
            ?: File("/storage/emulated/0/${names[0]}")
    }
    var games: List<Game> = emptyList(); private set
    var bySys: Map<String, List<Game>> = emptyMap(); private set
    var byGenre: Map<String, List<Game>> = emptyMap(); private set
    /** Name of a system trailer and logo, from the old frontend's main menu art. */
    val menuWheel = HashMap<String, String>()
    val menuVideo = HashMap<String, String>()

    private val GAME = Regex("""<game name="([^"]*)"[^>]*>([\s\S]*?)</game>""")
    private val DISC = Regex("""^(.*?)\s*\(Disc (\d+)\)(.*)$""")
    private fun tag(body: String, name: String) =
        Regex("<$name>([\\s\\S]*?)</$name>").find(body)?.groupValues?.get(1)?.trim()?.let(::unescape) ?: ""

    private fun unescape(s: String) = s.replace("&amp;", "&").replace("&apos;", "'").replace("&quot;", "\"")
        .replace("&lt;", "<").replace("&gt;", ">")

    /** Folders made on Windows only match if case is ignored. The first of the names that exists. */
    private fun child(parent: File, vararg names: String): File? {
        for (name in names) {
            File(parent, name).takeIf { it.exists() }?.let { return it }
            parent.listFiles()?.firstOrNull { it.name.equals(name, ignoreCase = true) }?.let { return it }
        }
        return null
    }

    private fun index(dir: File?): Map<String, String> {
        val out = HashMap<String, String>()
        dir?.listFiles()?.forEach { f -> if (f.isFile) out[f.name.substringBeforeLast('.').lowercase()] = f.path }
        return out
    }

    private val cacheFile get() = File(Stats.dir, "catalog.json")

    /** Last run's catalog, so the shelves appear at once. False the very first time. */
    fun loadCache(): Boolean = runCatching {
        val j = JSONObject(cacheFile.readText())
        val systems = SYSTEMS.associateBy { it.id }
        val all = ArrayList<Game>()
        val arr = j.getJSONArray("games")
        for (i in 0 until arr.length()) {
            val o = arr.getJSONObject(i)
            val sys = systems[o.getString("s")] ?: continue
            val d = o.getJSONArray("d")
            val g = Game(
                sys, o.getString("b"), o.getString("t"), o.optString("y"), o.optString("m"),
                o.optString("g").ifEmpty { null }, List(d.length()) { File(d.getString(it)) },
                o.optString("bx").ifEmpty { null }, o.optString("ct").ifEmpty { null },
                o.optString("wh").ifEmpty { null }, o.optString("v").ifEmpty { null }, o.optString("sh", BACK), o.optString("c").ifEmpty { null }, o.optInt("p"),
            )
            g.aspect = o.optDouble("a", .72).toFloat()
            all += g
        }
        fun map(name: String, into: HashMap<String, String>) {
            val m = j.getJSONObject(name)
            m.keys().forEach { into[it] = m.getString(it) }
        }
        map("wheel", menuWheel)
        map("video", menuVideo)
        publish(all)
        all.isNotEmpty()
    }.getOrDefault(false)

    private fun saveCache() {
        runCatching {
            val arr = JSONArray()
            for (g in games) {
                arr.put(JSONObject().put("s", g.sys.id).put("b", g.base).put("t", g.title).put("y", g.year).put("m", g.maker)
                    .put("g", g.genre ?: "").put("d", JSONArray(g.discs.map { it.path }))
                    .put("bx", g.box ?: "").put("ct", g.cart ?: "").put("wh", g.wheel ?: "").put("v", g.video ?: "")
                    .put("sh", g.earned).put("c", g.core ?: "").put("p", g.players).put("a", g.aspect.toDouble()))
            }
            val tmp = File(Stats.dir, "catalog.json.tmp")
            tmp.writeText(JSONObject().put("games", arr).put("wheel", JSONObject(menuWheel as Map<*, *>)).put("video", JSONObject(menuVideo as Map<*, *>)).toString())
            tmp.renameTo(cacheFile)
        }
    }

    private fun publish(all: List<Game>) {
        games = all
        bySys = all.groupBy { it.sys.id }
        byGenre = all.filter { it.genre != null && it.listed }.groupBy { it.genre!! }
    }

    /** A game changed shelves. */
    fun reshelve() = publish(games)

    /** Everything that shows, so art or a catalogue entry changed later still gets picked up. */
    private fun print(list: List<Game>) = list.map { listOf(it.rom.path, it.box, it.wheel, it.video, it.title, it.year, it.maker, it.genre, it.earned, it.core, it.players) }.toSet()

    /** The optional catalogue (docs/library.md): the name, facts and shelf of every game it knows. Beats a HyperSpin database. */
    private fun library(): JSONObject? = runCatching { JSONObject(File(Stats.dir, "library.json").readText()) }.getOrNull()

    private fun entry(lib: JSONObject?, s: Sys, key: String, title: String, year: String, maker: String, genre: String?, shelf: String,
                      discs: List<File>, box: String?, cart: String?, wheel: String?, video: String?): Game {
        val e = lib?.optJSONObject("${s.id}/$key")
        return Game(
            s, key, e?.optString("t")?.ifEmpty { null } ?: title, e?.optString("y")?.ifEmpty { null } ?: year, e?.optString("m")?.ifEmpty { null } ?: maker,
            e?.optString("g")?.ifEmpty { null } ?: genre, discs, box, cart, wheel, video, e?.optString("sh")?.ifEmpty { null } ?: shelf,
            e?.optString("c")?.ifEmpty { null }, e?.optString("p")?.toIntOrNull() ?: 0,
        )
    }

    /** Walk the real folders. Returns true if the library changed since what's on the shelves. */
    fun scan(): Boolean {
        val before = print(games)
        val all = ArrayList<Game>()
        val lib = library()
        val media = child(ROOT, "Media")
        val menu = media?.let { child(it, "Main Menu") }
        val menuImages = menu?.let { child(it, "Images") }
        menuWheel.putAll(index(menuImages?.let { child(it, "Wheel") }))
        menuVideo.putAll(index(menu?.let { child(it, "Video") }))
        for (s in SYSTEMS) {
            // Roms/snes, or HyperSpin's Roms/Super Nintendo Entertainment System/roms
            val romDir = child(File(ROOT, "Roms"), s.id, s.roms)?.let { child(it, "roms") ?: it } ?: continue
            val roms = HashMap<String, File>()
            romDir.listFiles()?.forEach { f ->
                if (f.isFile && f.extension.lowercase() in s.exts && !f.name.startsWith("[BIOS]")) roms[f.nameWithoutExtension.lowercase()] = f
            }
            if (roms.isEmpty()) continue
            val m = media?.let { child(it, s.id, s.media) }
            val img = m?.let { child(it, "Images") ?: it }
            val boxes = index(img?.let { child(it, "Box", "Artwork3") })
            val carts = index(img?.let { child(it, "Cart", "Artwork4") })
            val wheels = index(img?.let { child(it, "Logo", "Wheel") })
            val videos = index(m?.let { child(it, "Video") })
            val seen = HashSet<String>()
            val xml = File(ROOT, "Databases/${s.db}/${s.db}.xml")
            val text = if (xml.isFile) xml.readText() else ""
            val groups = LinkedHashMap<String, MutableList<Pair<Int, File>>>()
            val meta = HashMap<String, Array<String>>()
            for (m2 in GAME.findAll(text)) {
                val name = unescape(m2.groupValues[1])
                val rom = roms[name.lowercase()] ?: continue
                seen += name.lowercase()
                // a zip in the arcade folder may only be another game's parent or BIOS: the catalogue says which are games
                if (s.id == "arcade" && lib != null && !lib.has("arcade/$name")) continue
                val d = DISC.find(name)
                val key = if (d != null) d.groupValues[1] + d.groupValues[3] else name
                val disc = d?.groupValues?.get(2)?.toInt() ?: 1
                groups.getOrPut(key) { ArrayList() } += disc to rom
                if (key !in meta || disc == 1) {
                    val body = m2.groupValues[2]
                    meta[key] = arrayOf(name, tag(body, "description"), tag(body, "year"), tag(body, "manufacturer"), tag(body, "genre"))
                }
            }
            for ((key, discs) in groups) {
                val mm = meta.getValue(key)
                val art = mm[0].lowercase()
                all += entry(
                    lib, s, key, prettyTitle(mm[1].ifEmpty { key }.replace(DISC_TAG, "")),
                    mm[2], mm[3], normalGenre(mm[4]), PICK, discs.sortedBy { it.first }.map { it.second },
                    boxes[art], carts[art], wheels[art], videos[art],
                )
            }
            // anything else in the rom folder still shows up: on the shelves with no catalogue, else in the back room
            run {
                val extra = LinkedHashMap<String, MutableList<Pair<Int, File>>>()
                for ((low, f) in roms) {
                    if (low in seen) continue
                    if (s.id == "arcade" && lib != null && !lib.has("arcade/${f.nameWithoutExtension}")) continue
                    val d = DISC.find(f.nameWithoutExtension)
                    val key = if (d != null) d.groupValues[1] + d.groupValues[3] else f.nameWithoutExtension
                    extra.getOrPut(key) { ArrayList() } += (d?.groupValues?.get(2)?.toInt() ?: 1) to f
                }
                for ((key, discs) in extra) {
                    val art = key.lowercase()
                    all += entry(
                        lib, s, key, prettyTitle(key.replace(TAGS, "").replace('_', ' ').trim()), "", "", null, if (lib == null) PICK else BACK,
                        discs.sortedBy { it.first }.map { it.second },
                        boxes[art], carts[art], wheels[art], videos[art],
                    )
                }
            }
        }
        all.sortBy { it.title.lowercase() }
        loadAspects(all)
        val changed = print(all) != before
        if (changed) {
            publish(all)
            saveCache()
        }
        return changed
    }

    private val DISC_TAG = Regex("""\s*\(Disc \d+\)""")
    private val TAGS = Regex("""\s*[\(\[][^)\]]*[\)\]]""")

    private fun prettyTitle(t: String): String {
        val m = Regex("""^(.*?), (The|A|An)( - .*)?$""").find(t.trim()) ?: return t.trim()
        return m.groupValues[2] + " " + m.groupValues[1] + m.groupValues[3]
    }

    /** Box shapes, so shelves can stand each one at its true width. Kept between runs. */
    private fun loadAspects(games: List<Game>) {
        val cacheFile = File(Stats.dir, "aspects.json")
        val cache = runCatching { JSONObject(cacheFile.readText()) }.getOrDefault(JSONObject())
        var dirty = false
        val o = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        for (g in games) {
            val box = g.box ?: continue
            var a = cache.optDouble(box, 0.0).toFloat()
            if (a <= 0f) {
                BitmapFactory.decodeFile(box, o)
                if (o.outHeight > 0) {
                    a = o.outWidth.toFloat() / o.outHeight
                    cache.put(box, a.toDouble())
                    dirty = true
                }
            }
            if (a > 0f) g.aspect = a.coerceIn(.55f, 1.5f)
        }
        if (dirty) runCatching { cacheFile.writeText(cache.toString()) }
    }

    fun normalGenre(raw: String): String? {
        val g = raw.lowercase()
        return when {
            g.isBlank() || g == "miscellaneous" -> null
            "platform" in g || "plkatform" in g -> "Platformers"
            "role" in g -> "RPGs"
            "beat" in g -> "Beat 'em ups"
            "shoot-'em" in g || "shoot 'em" in g || "shmup" in g -> "Shoot 'em ups"
            "fight" in g || "versus" in g || "boxing" in g || "wrestling" in g -> "Fighting"
            "shooter" in g || "gun" in g -> "Shooters"
            "driving" in g || "motorcycle" in g || "water" in g || "racing" in g || "flying" in g -> "Racing"
            "sport" in g || "snowboard" in g || "golf" in g || "skate" in g -> "Sports"
            "puzzle" in g -> "Puzzle"
            "strategy" in g || "simulation" in g || "virtual" in g -> "Strategy"
            "party" in g || "mini" in g || "board" in g || "card" in g || "pool" in g || "compilation" in g || "rhythm" in g || "pinball" in g -> "Party"
            "adventure" in g -> "Adventure"
            "action" in g -> "Action"
            else -> null
        }
    }
}
