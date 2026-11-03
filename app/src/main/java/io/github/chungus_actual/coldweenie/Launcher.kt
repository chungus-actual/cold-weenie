package io.github.chungus_actual.coldweenie

import android.app.AppOpsManager
import android.app.usage.UsageEvents
import android.app.usage.UsageStatsManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Process
import android.os.SystemClock
import java.io.File

/** Starting a game, and RetroArch's resume state for it. */
object Launcher {
    private const val RA = "com.retroarch.aarch64"
    private const val RA_ACTIVITY = "com.retroarch.browser.retroactivity.RetroActivityFuture"
    private const val MAX_SESSION = 6 * 3600L
    private val STATES = File("/storage/emulated/0/RetroArch/states")

    fun intent(g: Game, disc: Int): Intent {
        val rom = g.discs[disc].path
        val i = Intent().addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
        when (val l = g.sys.launch) {
            is Launch.Core -> i.setComponent(ComponentName(RA, RA_ACTIVITY))
                .putExtra("ROM", rom)
                .putExtra("LIBRETRO", "/data/user/0/$RA/cores/${g.core ?: l.core}_libretro_android.so")
                .putExtra("CONFIGFILE", "/storage/emulated/0/Android/data/$RA/files/retroarch.cfg")
                .putExtra("QUITFOCUS", "")
            Launch.Flycast -> i.setComponent(ComponentName("com.flycast.emulator", "com.flycast.emulator.MainActivity"))
                .setAction(Intent.ACTION_VIEW).setData(Uri.parse(rom))
            Launch.Dolphin -> i.setComponent(ComponentName("org.dolphinemu.dolphinemu", "org.dolphinemu.dolphinemu.ui.main.TvMainActivity"))
                .setAction(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LEANBACK_LAUNCHER)
                .putExtra("AutoStartFile", rom)
            Launch.Ppsspp -> i.setComponent(ComponentName("org.ppsspp.ppsspp", "org.ppsspp.ppsspp.PpssppActivity"))
                .setAction(Intent.ACTION_VIEW).setData(Uri.fromFile(File(rom)))
        }
        return i
    }

    fun start(ctx: Context, g: Game, disc: Int): Boolean = runCatching {
        ctx.startActivity(intent(g, disc))
        Stats.started(g, disc, intent(g, disc).component!!.packageName, SystemClock.uptimeMillis())
        true
    }.getOrDefault(false)

    /** Count the game that was running, if there is one. Safe to call any time we come to the front. */
    fun settle(ctx: Context) {
        val o = Stats.open() ?: return
        val at = o.optLong("t")
        val up = o.optLong("u")
        val secs = onScreen(ctx, o.optString("p"), at, System.currentTimeMillis())
            ?: if (SystemClock.uptimeMillis() >= up) (SystemClock.uptimeMillis() - up) / 1000 else 0L
        // capped: an emulator keeps the screen awake, so a game left running overnight shouldn't count as a marathon
        Stats.finished(o.optString("g"), at, secs.coerceAtMost(MAX_SESSION))
    }

    /** Seconds the emulator was on screen, from the system's own record. Null without the usage permission (see README). */
    private fun onScreen(ctx: Context, pkg: String, from: Long, to: Long): Long? {
        val ops = ctx.getSystemService(AppOpsManager::class.java)
        if (ops.checkOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS, Process.myUid(), ctx.packageName) != AppOpsManager.MODE_ALLOWED) return null
        val events = ctx.getSystemService(UsageStatsManager::class.java).queryEvents(from, to) ?: return null
        val e = UsageEvents.Event()
        var total = 0L
        var since = -1L
        while (events.hasNextEvent()) {
            events.getNextEvent(e)
            if (e.packageName != pkg) continue
            when (e.eventType) {
                UsageEvents.Event.MOVE_TO_FOREGROUND -> if (since < 0) since = e.timeStamp
                UsageEvents.Event.MOVE_TO_BACKGROUND -> if (since >= 0) {
                    total += e.timeStamp - since
                    since = -1
                }
            }
        }
        if (since >= 0) total += to - since
        return total / 1000
    }

    private fun stateFile(g: Game, disc: Int) = File(STATES, g.discs[disc].nameWithoutExtension + ".state.auto")

    fun hasResume(g: Game, disc: Int) = g.sys.launch is Launch.Core && stateFile(g, disc).isFile

    /** The frame RetroArch saved beside its resume state: the picture on a Keep playing tile. */
    fun resumeFrame(g: Game): String? {
        if (g.sys.launch !is Launch.Core) return null
        val f = File(stateFile(g, Stats.disc(g)).path + ".png")
        return if (f.isFile) f.path else null
    }

    /** Start over keeps the old state aside rather than deleting anybody's progress. */
    fun setAsideResume(g: Game, disc: Int) {
        val f = stateFile(g, disc)
        if (f.isFile) f.renameTo(File(f.path + ".old"))
        File(f.path + ".png").let { if (it.isFile) it.renameTo(File(it.path + ".old")) }
    }
}
