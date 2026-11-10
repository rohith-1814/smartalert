plugins {
    id("com.android.application")
}

android {
    namespace = "org.smartalert.app"
    compileSdk = 35
    buildToolsVersion = "35.0.0"

    defaultConfig {
        applicationId = "org.smartalert.app"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "1.0.0-demo"
    }
}
