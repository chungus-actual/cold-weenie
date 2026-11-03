package io.github.chungus_actual.coldweenie

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.util.LruCache
import java.util.concurrent.LinkedBlockingDeque
import kotlin.concurrent.thread

/** Decodes art off the UI thread, newest request first, so whatever is on screen arrives first. */
class Art(private val changed: () -> Unit) {
    private val cache = object : LruCache<String, Bitmap>(160 * 1024 * 1024) {
        override fun sizeOf(key: String, value: Bitmap) = value.allocationByteCount
    }
    private val pending = LinkedBlockingDeque<Pair<String, Int>>()
    private val asked = HashSet<String>()

    init {
        repeat(2) {
            thread(isDaemon = true, name = "art") {
                while (true) {
                    val (path, h) = pending.takeFirst()
                    val bmp = decode(path, h)
                    if (bmp != null) synchronized(cache) { cache.put(key(path, h), bmp) }
                    changed()
                }
            }
        }
    }

    private fun key(path: String, h: Int) = "$h|$path"

    /** The bitmap if it is ready, else null and it gets queued. */
    fun get(path: String?, h: Int): Bitmap? {
        path ?: return null
        val k = key(path, h)
        synchronized(cache) { cache.get(k) }?.let { return it }
        if (asked.size > 4000) asked.clear()
        if (asked.add(k)) pending.addFirst(path to h)
        return null
    }

    private fun decode(path: String, h: Int): Bitmap? = runCatching {
        val o = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(path, o)
        if (o.outHeight <= 0) return null
        o.inJustDecodeBounds = false
        o.inSampleSize = 1
        while (o.outHeight / (o.inSampleSize * 2) >= h) o.inSampleSize *= 2
        BitmapFactory.decodeFile(path, o)?.also { it.prepareToDraw() }
    }.getOrNull()
}
