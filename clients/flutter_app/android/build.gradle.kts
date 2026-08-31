allprojects {
    repositories {
        google()
        mavenCentral()
    }
}

val mobileReleaseBundletool by configurations.creating {
    isCanBeConsumed = false
    isCanBeResolved = true
    attributes {
        attribute(
            Usage.USAGE_ATTRIBUTE,
            objects.named(Usage.JAVA_RUNTIME),
        )
        attribute(
            Category.CATEGORY_ATTRIBUTE,
            objects.named(Category.LIBRARY),
        )
        attribute(
            LibraryElements.LIBRARY_ELEMENTS_ATTRIBUTE,
            objects.named(LibraryElements.JAR),
        )
        attribute(
            TargetJvmEnvironment.TARGET_JVM_ENVIRONMENT_ATTRIBUTE,
            objects.named(TargetJvmEnvironment.STANDARD_JVM),
        )
    }
    resolutionStrategy.force(
        "com.android.tools.build:aapt2-proto:9.1.0-14792394",
        "com.google.code.gson:gson:2.11.0",
        "com.google.guava:guava:33.3.1-jre",
        "com.google.protobuf:protobuf-java:3.25.5",
        "com.google.protobuf:protobuf-java-util:3.25.5",
    )
}

dependencies {
    add(mobileReleaseBundletool.name, "com.android.tools.build:bundletool:1.18.3")
}

fun JavaExec.configureMobileReleaseBundletool(vararg command: String) {
    classpath = mobileReleaseBundletool
    mainClass.set("com.android.tools.build.bundletool.BundleToolMain")
    jvmArgs("-Dfile.encoding=UTF-8")
    doFirst {
        val bundle = providers.gradleProperty("mobileReleaseBundle").orNull
            ?: throw GradleException("mobile release bundle path is required")
        args(*command, "--bundle=${file(bundle).canonicalPath}")
    }
}

tasks.register<JavaExec>("verifyCandidateBundle") {
    configureMobileReleaseBundletool("validate")
}

tasks.register<JavaExec>("dumpCandidateManifest") {
    configureMobileReleaseBundletool("dump", "manifest")
}

val newBuildDir: Directory =
    rootProject.layout.buildDirectory
        .dir("../../build")
        .get()
rootProject.layout.buildDirectory.value(newBuildDir)

subprojects {
    val newSubprojectBuildDir: Directory = newBuildDir.dir(project.name)
    project.layout.buildDirectory.value(newSubprojectBuildDir)
}
subprojects {
    project.evaluationDependsOn(":app")
    if (name == "flutter_line_sdk") {
        afterEvaluate {
            extensions.configure<com.android.build.api.dsl.LibraryExtension> {
                // 2.7.2 pins 33, while its resolved AndroidX metadata requires 34+.
                compileSdk = 36
            }
        }
    }
}

tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}
