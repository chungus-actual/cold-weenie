package io.github.chungus_actual.coldweenie

import android.hardware.input.InputManager
import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.PixelFormat
import android.graphics.drawable.ColorDrawable
import android.media.AudioAttributes
import android.media.SoundPool
import android.os.Bundle
import android.os.StrictMode
import android.speech.RecognizerIntent
import android.view.KeyEvent
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.FrameLayout
import kotlin.concurrent.thread

class MainActivity : Activity(), Room.Host {
    private lateinit var crt: Crt
    private lateinit var room: Room
    private var rain: RainGlass? = null
    private lateinit var pool: SoundPool
    private val sounds = HashMap<String, Int>()
    private var loaded = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // emulators are handed file:// paths: they live on the same storage, nothing leaves the box
        StrictMode.setVmPolicy(StrictMode.VmPolicy.Builder().build())
        window.setFormat(PixelFormat.TRANSLUCENT)
        window.setBackgroundDrawable(ColorDrawable(0))
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        Geo.load(this, nextRoom())
        crt = Crt(this)
        room = Room(this, crt, this)
        val root = FrameLayout(this)
        root.addView(crt)
        if (Geo.glass.isNotEmpty()) rain = RainGlass(this).also { root.addView(it) }
        root.addView(room, ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        root.addOnLayoutChangeListener { _, _, _, r, _, _, _, _, _ ->
            val s = r / 1920f
            val lp = crt.layoutParams as FrameLayout.LayoutParams
            val box = Geo.screenBox()
            val w = (box.width() * s).toInt()
            if (lp.width != w) {
                lp.width = w
                lp.height = (box.height() * s).toInt()
                lp.leftMargin = (box.left * s).toInt()
                lp.topMargin = (box.top * s).toInt()
                crt.quad = FloatArray(8) { i -> (Geo.screen[i] - (if (i % 2 == 0) box.left else box.top)) * s }
                crt.post { crt.requestLayout() }
                rain?.let { g ->
                    val rl = g.layoutParams as FrameLayout.LayoutParams
                    rl.leftMargin = (Geo.glass[0] * s).toInt()
                    rl.topMargin = (Geo.glass[1] * s).toInt()
                    rl.width = (Geo.glass[2] * s).toInt() + 1
                    rl.height = (Geo.glass[3] * s).toInt() + 1
                    g.post { g.requestLayout() }
                }
            }
        }
        setContentView(root)
        room.isFocusable = true
        room.isFocusableInTouchMode = true
        room.requestFocus()

        pool = SoundPool.Builder().setMaxStreams(4)
            .setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_GAME).setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build())
            .build()
        for (n in listOf("tick", "thunk", "static", "back", "power")) {
            assets.openFd("sfx/$n.wav").use { sounds[n] = pool.load(it, 1) }
        }

        if (checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) == PackageManager.PERMISSION_GRANTED) {
            load()
        } else {
            requestPermissions(arrayOf(Manifest.permission.READ_EXTERNAL_STORAGE, Manifest.permission.WRITE_EXTERNAL_STORAGE), 1)
        }
    }

    /** A different room each time the app starts, or the one named by `am start -e room <name>`. */
    private fun nextRoom(): String {
        intent.getStringExtra("room")?.takeIf { it in Geo.ROOMS }?.let { return it }
        val prefs = getSharedPreferences("basement", MODE_PRIVATE)
        val i = prefs.getInt("room", -1) + 1
        prefs.edit().putInt("room", i).apply()
        return Geo.ROOMS[i % Geo.ROOMS.size]
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        if (grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED) load()
    }

    /** A controller switching on or off changes the home screen while you're looking at it. */
    private val padWatch = object : InputManager.InputDeviceListener {
        override fun onInputDeviceAdded(id: Int) = padsChanged()
        override fun onInputDeviceRemoved(id: Int) = padsChanged()
        override fun onInputDeviceChanged(id: Int) = Unit
    }
    private var pads = -1

    private fun padsChanged() {
        val now = Pads.count()
        if (now == pads) return
        val mattered = maxOf(now, pads) >= 2
        pads = now
        if (loaded && mattered) room.refresh(Rows.home())
    }

    private fun load() {
        thread(name = "catalog") {
            val cached = Catalog.loadCache()
            if (!cached) Catalog.scan()
            val home = Rows.home()
            runOnUiThread {
                loaded = true
                room.show(home)
            }
            // anything added since last time turns up without anyone waiting for it
            if (cached && Catalog.scan()) {
                val fresh = Rows.home()
                runOnUiThread { room.refresh(fresh) }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        crt.onResume()
        rain?.onResume()
        hideBars()
        Launcher.settle(this)
        pads = Pads.count()
        getSystemService(InputManager::class.java).registerInputDeviceListener(padWatch, null)
        if (loaded) room.refresh(Rows.home())
    }

    override fun onPause() {
        getSystemService(InputManager::class.java).unregisterInputDeviceListener(padWatch)
        super.onPause()
        crt.off()
        crt.onPause()
        rain?.onPause()
    }

    private fun hideBars() {
        window.decorView.systemUiVisibility = (View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY or View.SYSTEM_UI_FLAG_LAYOUT_STABLE or
            View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION or View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN or
            View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or View.SYSTEM_UI_FLAG_FULLSCREEN)
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent): Boolean {
        if (room.key(keyCode, event.repeatCount)) return true
        return super.onKeyDown(keyCode, event)
    }

    override fun play(g: Game, disc: Int) {
        room.postDelayed({ Launcher.start(this, g, disc) }, 140)
    }

    override fun leave() {
        finish()
    }

    private val speech get() = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
        .putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
        .putExtra(RecognizerIntent.EXTRA_PROMPT, "Name a game")

    override val canListen by lazy { packageManager.queryIntentActivities(speech, 0).isNotEmpty() }

    override fun listen() {
        if (canListen) runCatching { startActivityForResult(speech, VOICE) }
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != VOICE || resultCode != RESULT_OK) return
        data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)?.firstOrNull()?.let { room.heard(it) }
    }

    override fun sound(name: String) {
        sounds[name]?.let { pool.play(it, .55f, .55f, 1, 0, 1f) }
    }

    private companion object {
        const val VOICE = 7
    }
}
