// Cold Weenie: a couch launcher for retro games. No third-party libraries: the Android SDK, Kotlin's
// standard library and OpenGL ES.
//
// Build switches (all optional):
//   -PappId=<id>      the applicationId (default io.github.chungus_actual.coldweenie)
//   -Pdata=<folder>   where stats and library.json live, under /sdcard (default ColdWeenie)
//   -Plibrary=<a,b>   folder names to look for the games under, first found wins (default Games,Hyperspin)
//   KEYSTORE_FILE, KEYSTORE_PASSWORD, KEY_ALIAS, KEY_PASSWORD (environment)
//                     sign the release build with that key; without them it is signed with the debug key
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "io.github.chungus_actual.coldweenie"
    compileSdk = 34

    defaultConfig {
        applicationId = (project.findProperty("appId") as String?) ?: "io.github.chungus_actual.coldweenie"
        minSdk = 28
        // 28 on purpose: the emulators are handed plain file paths
        targetSdk = 28
        versionCode = 1
        versionName = "0.1.0"
        buildConfigField("String", "DATA_DIR", "\"${project.findProperty("data") ?: "ColdWeenie"}\"")
        buildConfigField("String", "LIBRARY", "\"${project.findProperty("library") ?: "Games,Hyperspin"}\"")
    }

    buildFeatures {
        buildConfig = true
    }

    val keystore = System.getenv("KEYSTORE_FILE")
    signingConfigs {
        if (keystore != null) {
            create("release") {
                storeFile = file(keystore)
                storePassword = System.getenv("KEYSTORE_PASSWORD")
                keyAlias = System.getenv("KEY_ALIAS")
                keyPassword = System.getenv("KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName(if (keystore != null) "release" else "debug")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    lint {
        checkReleaseBuilds = false
    }
}
