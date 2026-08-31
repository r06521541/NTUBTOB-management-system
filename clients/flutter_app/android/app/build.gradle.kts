import java.net.URI
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import java.util.Base64

import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.TaskAction

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

class MobileReleaseConfig(
    val releaseChannel: String,
    val applicationId: String,
    val versionCode: Int,
    val previousVersionCode: Int,
    val versionName: String,
    val keyStore: File,
    val keyAlias: String,
    val storePassword: String,
    val keyPassword: String,
    val apiOriginSha256: String,
    val providerConfigSha256: String,
    val contractTest: Boolean,
)

abstract class GenerateMobileReleaseContract : DefaultTask() {
    @get:Input
    abstract val contractContents: Property<String>

    @get:OutputDirectory
    abstract val outputDirectory: DirectoryProperty

    @TaskAction
    fun generate() {
        val output = outputDirectory.file("mobile-release-contract.properties").get().asFile
        output.parentFile.mkdirs()
        output.writeText(contractContents.get(), StandardCharsets.UTF_8)
    }
}

fun requiredReleaseEnvironment(name: String, secret: Boolean = false): String {
    val value = System.getenv(name)
        ?: throw GradleException("$name is required for every Android release build")
    if (value.isEmpty() || (!secret && value != value.trim())) {
        throw GradleException("$name is empty or padded")
    }
    return value
}

fun decodeDartDefines(encoded: String?): Map<String, String> {
    if (encoded.isNullOrBlank()) {
        throw GradleException("dart-defines are required for every Android release build")
    }
    val result = linkedMapOf<String, String>()
    encoded.split(',').forEach { item ->
        val decoded = try {
            String(Base64.getDecoder().decode(item), StandardCharsets.UTF_8)
        } catch (_: IllegalArgumentException) {
            throw GradleException("dart-defines contain malformed base64")
        }
        val separator = decoded.indexOf('=')
        if (separator <= 0) {
            throw GradleException("dart-defines contain a malformed entry")
        }
        val key = decoded.substring(0, separator)
        val value = decoded.substring(separator + 1)
        if (result.putIfAbsent(key, value) != null) {
            throw GradleException("dart-defines contain duplicate entries")
        }
    }
    return result
}

fun sha256(value: String): String = MessageDigest.getInstance("SHA-256")
    .digest(value.toByteArray(StandardCharsets.UTF_8))
    .joinToString("") { "%02x".format(it) }

fun loadMobileReleaseConfig(): MobileReleaseConfig {
    val contractTest = when (System.getenv("MOBILE_RELEASE_CONTRACT_TEST")) {
        null, "false" -> false
        "true" -> true
        else -> throw GradleException("MOBILE_RELEASE_CONTRACT_TEST must be true, false, or absent")
    }
    val releaseChannel = requiredReleaseEnvironment("MOBILE_RELEASE_CHANNEL")
    if (releaseChannel != "android-closed") {
        throw GradleException("MOBILE_RELEASE_CHANNEL must be android-closed")
    }
    val expectedApplicationId = if (contractTest) {
        "tw.org.ntubtob.portal.contracttest"
    } else {
        "tw.org.ntubtob.portal"
    }
    val applicationId = requiredReleaseEnvironment("MOBILE_RELEASE_APPLICATION_ID")
    if (applicationId != expectedApplicationId) {
        throw GradleException("MOBILE_RELEASE_APPLICATION_ID is not approved for this release mode")
    }

    val expectedVersionName = flutter.versionName.toString()
    val expectedVersionCode = flutter.versionCode.toString()
    val versionName = requiredReleaseEnvironment("MOBILE_RELEASE_VERSION_NAME")
    val versionCodeSource = requiredReleaseEnvironment("MOBILE_RELEASE_VERSION_CODE")
    val versionCode = versionCodeSource.toIntOrNull()
        ?: throw GradleException("MOBILE_RELEASE_VERSION_CODE must be an integer")
    val previousVersionCodeSource = requiredReleaseEnvironment("MOBILE_RELEASE_PREVIOUS_VERSION_CODE")
    val previousVersionCode = previousVersionCodeSource.toIntOrNull()
        ?: throw GradleException("MOBILE_RELEASE_PREVIOUS_VERSION_CODE must be an integer")
    if (
        versionName != expectedVersionName ||
        versionCodeSource != expectedVersionCode ||
        versionCode < 1 ||
        previousVersionCode < 0 ||
        previousVersionCodeSource != previousVersionCode.toString() ||
        versionCode <= previousVersionCode ||
        versionName == "0.0.0" ||
        !Regex("^(?:0|[1-9][0-9]*)\\.[0-9]+\\.[0-9]+$").matches(versionName)
    ) {
        throw GradleException("release version is non-monotonic, debug-shaped, or differs from pubspec.yaml")
    }

    val defines = decodeDartDefines(providers.gradleProperty("dart-defines").orNull)
    val requiredReleaseDefines = setOf(
        "APP_FLAVOR",
        "CLIENT_MODE",
        "RELEASE_CHANNEL",
        "RELEASE_SCOPE",
        "API_BASE_URL",
        "LINE_CHANNEL_ID",
        "GOOGLE_CLIENT_ID",
        "GOOGLE_SERVER_CLIENT_ID",
    )
    val flutterBuildDefines = setOf(
        "FLUTTER_BUILD_NAME",
        "FLUTTER_BUILD_NUMBER",
    )
    val flutterMetadataDefines = setOf(
        "FLUTTER_VERSION",
        "FLUTTER_CHANNEL",
        "FLUTTER_GIT_URL",
        "FLUTTER_FRAMEWORK_REVISION",
        "FLUTTER_ENGINE_REVISION",
        "FLUTTER_DART_VERSION",
    )
    if (defines.keys != requiredReleaseDefines + flutterBuildDefines + flutterMetadataDefines) {
        throw GradleException("Android release dart-defines are missing or unexpected")
    }
    fun requiredDefine(name: String): String {
        val value = defines[name]
            ?: throw GradleException("$name is required for every Android release build")
        if (value.isEmpty() || value != value.trim()) {
            throw GradleException("$name is empty or padded")
        }
        return value
    }
    if (
        requiredDefine("FLUTTER_BUILD_NAME") != expectedVersionName ||
        requiredDefine("FLUTTER_BUILD_NUMBER") != expectedVersionCode
    ) {
        throw GradleException("Android release Flutter build version differs from pubspec.yaml")
    }
    val revisionPattern = Regex("^[0-9a-f]{10}$")
    val dartVersionPattern = Regex("^[0-9]+\\.[0-9]+\\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
    if (
        defines["FLUTTER_VERSION"] != "3.47.0" ||
        defines["FLUTTER_CHANNEL"] != "stable" ||
        defines["FLUTTER_GIT_URL"] != "https://github.com/flutter/flutter.git" ||
        !revisionPattern.matches(requiredDefine("FLUTTER_FRAMEWORK_REVISION")) ||
        !revisionPattern.matches(requiredDefine("FLUTTER_ENGINE_REVISION")) ||
        !dartVersionPattern.matches(requiredDefine("FLUTTER_DART_VERSION"))
    ) {
        throw GradleException("Android release Flutter metadata is missing, unexpected, or unpinned")
    }
    if (requiredDefine("RELEASE_CHANNEL") != releaseChannel) {
        throw GradleException("Android release RELEASE_CHANNEL must be android-closed")
    }
    if (requiredDefine("APP_FLAVOR") != "staging") {
        throw GradleException("Android Closed Testing APP_FLAVOR must be staging")
    }
    if (requiredDefine("CLIENT_MODE") != "real") {
        throw GradleException("Android release CLIENT_MODE must be real")
    }
    val releaseScope = "basic"
    if (defines["RELEASE_SCOPE"] != releaseScope) {
        throw GradleException("Android release RELEASE_SCOPE must be explicitly basic")
    }

    val apiOrigin = requiredDefine("API_BASE_URL")
    val uri = try {
        URI(apiOrigin)
    } catch (_: Exception) {
        throw GradleException("API_BASE_URL is malformed")
    }
    if (
        uri.scheme != "https" ||
        uri.host.isNullOrBlank() ||
        uri.userInfo != null ||
        uri.port !in setOf(-1, 443) ||
        uri.query != null ||
        uri.fragment != null ||
        !(uri.path.isNullOrEmpty() || uri.path == "/")
    ) {
        throw GradleException("API_BASE_URL must be an HTTPS origin without credentials or path")
    }
    val host = uri.host.lowercase()
    val privateIpv4 = Regex("^(?:10|127|169\\.254|192\\.168|172\\.(?:1[6-9]|2[0-9]|3[01]))\\.")
    if (contractTest) {
        if (apiOrigin != "https://mobile-release.invalid") {
            throw GradleException("contract-test release must use the fixed reserved API origin")
        }
    } else if (
        host == "localhost" ||
        "." !in host ||
        host.endsWith(".localhost") ||
        host.endsWith(".invalid") ||
        host.endsWith(".test") ||
        host.endsWith(".example") ||
        host in setOf("example.com", "example.net", "example.org") ||
        host.endsWith(".example.com") ||
        host.endsWith(".example.net") ||
        host.endsWith(".example.org") ||
        privateIpv4.containsMatchIn(host) ||
        host == "0.0.0.0" ||
        host == "::1"
    ) {
        throw GradleException("Android Closed Testing API_BASE_URL must not be local or reserved")
    }
    val expectedApiOriginSha256 = requiredReleaseEnvironment(
        "MOBILE_RELEASE_STAGING_API_ORIGIN_SHA256",
    )
    if (
        !Regex("^[0-9a-f]{64}$").matches(expectedApiOriginSha256) ||
        sha256(apiOrigin) != expectedApiOriginSha256
    ) {
        throw GradleException("API_BASE_URL does not match the approved staging origin digest")
    }

    val lineChannelId = requiredDefine("LINE_CHANNEL_ID")
    val googleClientId = requiredDefine("GOOGLE_CLIENT_ID")
    val googleServerClientId = requiredDefine("GOOGLE_SERVER_CLIENT_ID")
    val googlePattern = Regex("^[0-9A-Za-z][0-9A-Za-z._-]{5,199}\\.apps\\.googleusercontent\\.com$")
    if (!Regex("^[1-9][0-9]{4,19}$").matches(lineChannelId)) {
        throw GradleException("LINE_CHANNEL_ID is malformed")
    }
    if (
        !googlePattern.matches(googleClientId) ||
        !googlePattern.matches(googleServerClientId) ||
        googleClientId == googleServerClientId
    ) {
        throw GradleException("Google client IDs are missing, malformed, or mixed")
    }
    if (contractTest) {
        if (
            lineChannelId != "12345" ||
            googleClientId != "android-contract.apps.googleusercontent.com" ||
            googleServerClientId != "server-contract.apps.googleusercontent.com"
        ) {
            throw GradleException("contract-test provider IDs must use the fixed fictional values")
        }
    } else {
        val nonCandidateShape = Regex("(?i)(?:^|[-_.])(debug|dev|fake|test|contract)(?:$|[-_.])")
        if (
            nonCandidateShape.containsMatchIn(googleClientId) ||
            nonCandidateShape.containsMatchIn(googleServerClientId)
        ) {
            throw GradleException("candidate provider IDs must not be debug-shaped")
        }
    }
    val expectedProviderConfigSha256 = requiredReleaseEnvironment(
        "MOBILE_RELEASE_STAGING_PROVIDER_CONFIG_SHA256",
    )
    val providerConfig = listOf(
        lineChannelId,
        googleClientId,
        googleServerClientId,
    ).joinToString("\n")
    if (
        !Regex("^[0-9a-f]{64}$").matches(expectedProviderConfigSha256) ||
        sha256(providerConfig) != expectedProviderConfigSha256
    ) {
        throw GradleException("provider IDs do not match the approved staging configuration digest")
    }

    val keyStore = file(requiredReleaseEnvironment("MOBILE_RELEASE_KEYSTORE_PATH")).canonicalFile
    val repositoryRoot = rootProject.projectDir.parentFile.parentFile.parentFile.canonicalFile
    if (
        !keyStore.isFile ||
        keyStore.toPath().startsWith(repositoryRoot.toPath()) ||
        keyStore.extension.lowercase() !in setOf("jks", "keystore")
    ) {
        throw GradleException("MOBILE_RELEASE_KEYSTORE_PATH must be an external JKS/keystore file")
    }
    val keyAlias = requiredReleaseEnvironment("MOBILE_RELEASE_KEY_ALIAS")
    val storePassword = requiredReleaseEnvironment("MOBILE_RELEASE_STORE_PASSWORD", secret = true)
    val keyPassword = requiredReleaseEnvironment("MOBILE_RELEASE_KEY_PASSWORD", secret = true)
    if (storePassword.length < 8 || keyPassword.length < 8) {
        throw GradleException("release signing passwords must be externally supplied and nontrivial")
    }
    val debugShaped = Regex("(?i)(?:^|[-_.])(debug|dev|fake)(?:$|[-_.])")
    if (debugShaped.containsMatchIn(keyStore.name) || debugShaped.containsMatchIn(keyAlias)) {
        throw GradleException("release signing identity must not be debug-shaped")
    }
    if (contractTest && !keyAlias.contains("contract", ignoreCase = true)) {
        throw GradleException("contract-test signing alias must be visibly fictional")
    }
    if (!contractTest && keyAlias.contains("contract", ignoreCase = true)) {
        throw GradleException("candidate signing alias must not be contract-test shaped")
    }

    return MobileReleaseConfig(
        releaseChannel = releaseChannel,
        applicationId = applicationId,
        versionCode = versionCode,
        previousVersionCode = previousVersionCode,
        versionName = versionName,
        keyStore = keyStore,
        keyAlias = keyAlias,
        storePassword = storePassword,
        keyPassword = keyPassword,
        apiOriginSha256 = expectedApiOriginSha256,
        providerConfigSha256 = expectedProviderConfigSha256,
        contractTest = contractTest,
    )
}

val releaseRequested = gradle.startParameter.taskNames.any {
    it.contains("release", ignoreCase = true)
}
val mobileReleaseConfig = if (releaseRequested) loadMobileReleaseConfig() else null
val releaseContractDirectory = layout.buildDirectory.dir("generated/mobileReleaseContract/release")

android {
    namespace = "tw.org.ntubtob.portal"
    compileSdk = 36
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        applicationId = mobileReleaseConfig?.applicationId ?: "tw.org.ntubtob.portal"
        minSdk = 24
        targetSdk = 36
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        mobileReleaseConfig?.let { config ->
            create("mobileRelease") {
                storeFile = config.keyStore
                keyAlias = config.keyAlias
                storePassword = config.storePassword
                keyPassword = config.keyPassword
            }
        }
    }

    buildTypes {
        release {
            mobileReleaseConfig?.let {
                signingConfig = signingConfigs.getByName("mobileRelease")
            }
        }
    }
}

val generateMobileReleaseContract = mobileReleaseConfig?.let { config ->
    val values = sortedMapOf(
        "api_origin_sha256" to config.apiOriginSha256,
        "app_flavor" to "staging",
        "application_id" to config.applicationId,
        "client_mode" to "real",
        "compile_sdk" to "36",
        "contract_test" to config.contractTest.toString(),
        "previous_version_code" to config.previousVersionCode.toString(),
        "provider_config_sha256" to config.providerConfigSha256,
        "release_channel" to config.releaseChannel,
        "release_scope" to "basic",
        "schema" to "2",
        "target_sdk" to "36",
        "version_code" to config.versionCode.toString(),
        "version_name" to config.versionName,
    )
    tasks.register<GenerateMobileReleaseContract>("generateMobileReleaseContract") {
        contractContents.set(
            values.entries.joinToString(separator = "\n", postfix = "\n") {
                "${it.key}=${it.value}"
            },
        )
        outputDirectory.set(releaseContractDirectory)
    }
}

androidComponents {
    onVariants(selector().withBuildType("release")) { variant ->
        generateMobileReleaseContract?.let { taskProvider ->
            val releaseAssets = variant.sources.assets
                ?: throw GradleException("Android release assets source API is unavailable")
            releaseAssets.addGeneratedSourceDirectory(
                taskProvider,
                GenerateMobileReleaseContract::outputDirectory,
            )
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
