package com.zeeriz.fleetai.data.local

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

/**
 * Last successful API responses saved as JSON files, so screens still show data (marked "offline")
 * when the laptop server is not reachable during a demo.
 */
class ResponseCache(context: Context) {
    private val dir = File(context.filesDir, "api_cache").apply { mkdirs() }

    private fun file(key: String) = File(dir, key.replace(Regex("[^A-Za-z0-9_.-]"), "_") + ".json")

    suspend fun put(key: String, json: String) = withContext(Dispatchers.IO) {
        val target = file(key)
        val tmp = File(dir, target.name + ".tmp")
        tmp.writeText(json)
        tmp.renameTo(target)
    }

    /** Returns the cached JSON and when it was saved, or null. */
    suspend fun get(key: String): Pair<String, Long>? = withContext(Dispatchers.IO) {
        val f = file(key)
        if (f.exists()) f.readText() to f.lastModified() else null
    }

    suspend fun clear() = withContext(Dispatchers.IO) { dir.listFiles()?.forEach { it.delete() } }
}
