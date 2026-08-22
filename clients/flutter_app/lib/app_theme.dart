import 'package:flutter/material.dart';

const appBrandNavy = Color(0xff29415d);
const appBrandGold = Color(0xffc39a55);

abstract final class AppSpacing {
  static const double compact = 8;
  static const double regular = 16;
  static const double generous = 24;
}

@immutable
class AppVisualTokens extends ThemeExtension<AppVisualTokens> {
  const AppVisualTokens({
    required this.canvas,
    required this.surface,
    required this.text,
    required this.muted,
    required this.border,
    required this.accent,
    required this.success,
    required this.successSoft,
    required this.warning,
    required this.warningSoft,
    required this.danger,
    required this.dangerSoft,
  });

  final Color canvas;
  final Color surface;
  final Color text;
  final Color muted;
  final Color border;
  final Color accent;
  final Color success;
  final Color successSoft;
  final Color warning;
  final Color warningSoft;
  final Color danger;
  final Color dangerSoft;

  static const light = AppVisualTokens(
    canvas: Color(0xfff5f6f8),
    surface: Color(0xffffffff),
    text: Color(0xff18212b),
    muted: Color(0xff66717e),
    border: Color(0xffd9dee5),
    accent: appBrandGold,
    success: Color(0xff26734d),
    successSoft: Color(0xffe4f2ea),
    warning: Color(0xff8a641f),
    warningSoft: Color(0xfff8efd9),
    danger: Color(0xffa63d3d),
    dangerSoft: Color(0xfff8e7e7),
  );

  static const dark = AppVisualTokens(
    canvas: Color(0xff0f1720),
    surface: Color(0xff172330),
    text: Color(0xfff3f5f7),
    muted: Color(0xffb4bec8),
    border: Color(0xff41505f),
    accent: Color(0xffdfbc7d),
    success: Color(0xff78d6a5),
    successSoft: Color(0xff183c2c),
    warning: Color(0xffffd27d),
    warningSoft: Color(0xff493817),
    danger: Color(0xffffa5a5),
    dangerSoft: Color(0xff4e2628),
  );

  @override
  AppVisualTokens copyWith({
    Color? canvas,
    Color? surface,
    Color? text,
    Color? muted,
    Color? border,
    Color? accent,
    Color? success,
    Color? successSoft,
    Color? warning,
    Color? warningSoft,
    Color? danger,
    Color? dangerSoft,
  }) =>
      AppVisualTokens(
        canvas: canvas ?? this.canvas,
        surface: surface ?? this.surface,
        text: text ?? this.text,
        muted: muted ?? this.muted,
        border: border ?? this.border,
        accent: accent ?? this.accent,
        success: success ?? this.success,
        successSoft: successSoft ?? this.successSoft,
        warning: warning ?? this.warning,
        warningSoft: warningSoft ?? this.warningSoft,
        danger: danger ?? this.danger,
        dangerSoft: dangerSoft ?? this.dangerSoft,
      );

  @override
  AppVisualTokens lerp(covariant AppVisualTokens? other, double t) =>
      other == null
          ? this
          : AppVisualTokens(
              canvas: Color.lerp(canvas, other.canvas, t)!,
              surface: Color.lerp(surface, other.surface, t)!,
              text: Color.lerp(text, other.text, t)!,
              muted: Color.lerp(muted, other.muted, t)!,
              border: Color.lerp(border, other.border, t)!,
              accent: Color.lerp(accent, other.accent, t)!,
              success: Color.lerp(success, other.success, t)!,
              successSoft: Color.lerp(successSoft, other.successSoft, t)!,
              warning: Color.lerp(warning, other.warning, t)!,
              warningSoft: Color.lerp(warningSoft, other.warningSoft, t)!,
              danger: Color.lerp(danger, other.danger, t)!,
              dangerSoft: Color.lerp(dangerSoft, other.dangerSoft, t)!,
            );
}

extension AppThemeContext on BuildContext {
  AppVisualTokens get appTokens =>
      Theme.of(this).extension<AppVisualTokens>() ??
      (Theme.of(this).brightness == Brightness.light
          ? AppVisualTokens.light
          : AppVisualTokens.dark);
}

ThemeData appTheme(Brightness brightness) {
  final tokens = brightness == Brightness.light
      ? AppVisualTokens.light
      : AppVisualTokens.dark;
  final scheme = ColorScheme.fromSeed(
    seedColor: appBrandNavy,
    brightness: brightness,
    primary:
        brightness == Brightness.light ? appBrandNavy : const Color(0xffadc8e4),
    secondary: tokens.accent,
    surface: tokens.surface,
    error: tokens.danger,
  );
  final textTheme = ThemeData(brightness: brightness).textTheme.apply(
        bodyColor: tokens.text,
        displayColor: tokens.text,
      );
  const controlShape = RoundedRectangleBorder(
    borderRadius: BorderRadius.all(Radius.circular(12)),
  );
  return ThemeData(
    useMaterial3: true,
    brightness: brightness,
    colorScheme: scheme,
    extensions: [tokens],
    scaffoldBackgroundColor: tokens.canvas,
    textTheme: textTheme.copyWith(
      headlineLarge: textTheme.headlineLarge?.copyWith(
        fontWeight: FontWeight.w800,
        letterSpacing: -0.8,
      ),
      headlineSmall:
          textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800),
      titleLarge: textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
      titleMedium: textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
      labelLarge: textTheme.labelLarge?.copyWith(fontWeight: FontWeight.w800),
      bodySmall: textTheme.bodySmall?.copyWith(color: tokens.muted),
    ),
    appBarTheme: AppBarTheme(
      centerTitle: false,
      elevation: 0,
      backgroundColor: tokens.canvas,
      foregroundColor: tokens.text,
      surfaceTintColor: Colors.transparent,
      titleTextStyle: textTheme.titleLarge?.copyWith(
        color: tokens.text,
        fontWeight: FontWeight.w800,
      ),
    ),
    cardTheme: CardThemeData(
      elevation: 0,
      margin: EdgeInsets.zero,
      color: tokens.surface,
      surfaceTintColor: Colors.transparent,
      shadowColor: appBrandNavy.withValues(alpha: 0.12),
      shape: RoundedRectangleBorder(
        side: BorderSide(color: tokens.border),
        borderRadius: BorderRadius.circular(20),
      ),
    ),
    dividerColor: tokens.border,
    listTileTheme: ListTileThemeData(
      iconColor: scheme.primary,
      textColor: tokens.text,
      contentPadding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.regular,
        vertical: AppSpacing.compact,
      ),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: tokens.surface,
      constraints: const BoxConstraints(minHeight: 44),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide(color: tokens.border),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide(color: tokens.accent, width: 3),
      ),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        minimumSize: const Size(44, 44),
        backgroundColor: scheme.primary,
        foregroundColor: scheme.onPrimary,
        shape: controlShape,
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size(44, 44),
        shape: controlShape,
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size(44, 44),
        foregroundColor: scheme.primary,
        side: BorderSide(color: tokens.border),
        shape: controlShape,
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        minimumSize: const Size(44, 44),
        foregroundColor: scheme.primary,
        shape: controlShape,
      ),
    ),
    iconButtonTheme: const IconButtonThemeData(
      style: ButtonStyle(minimumSize: WidgetStatePropertyAll(Size(44, 44))),
    ),
    segmentedButtonTheme: SegmentedButtonThemeData(
      style: ButtonStyle(
        minimumSize: const WidgetStatePropertyAll(Size(44, 44)),
        shape: const WidgetStatePropertyAll(controlShape),
        side: WidgetStatePropertyAll(BorderSide(color: tokens.border)),
      ),
    ),
    chipTheme: ChipThemeData(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(999)),
      side: BorderSide(color: tokens.border),
    ),
    bannerTheme: MaterialBannerThemeData(
      backgroundColor: tokens.warningSoft,
      contentTextStyle: textTheme.bodyMedium?.copyWith(color: tokens.warning),
      padding: const EdgeInsets.all(AppSpacing.regular),
    ),
    navigationBarTheme: NavigationBarThemeData(
      height: 72,
      backgroundColor: tokens.surface,
      indicatorColor: scheme.primaryContainer,
      labelTextStyle: WidgetStatePropertyAll(
        textTheme.labelMedium?.copyWith(fontWeight: FontWeight.w700),
      ),
    ),
    focusColor: tokens.accent.withValues(alpha: 0.24),
  );
}

enum AppStatusTone { neutral, success, warning, danger }

class AppPageTitle extends StatelessWidget {
  const AppPageTitle({
    super.key,
    required this.eyebrow,
    required this.title,
    this.subtitle,
  });

  final String eyebrow;
  final String title;
  final String? subtitle;

  @override
  Widget build(BuildContext context) => Semantics(
        header: true,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              eyebrow.toUpperCase(),
              style: Theme.of(context).textTheme.labelLarge?.copyWith(
                    color: context.appTokens.accent,
                    letterSpacing: 1.2,
                  ),
            ),
            const SizedBox(height: AppSpacing.compact),
            Text(title, style: Theme.of(context).textTheme.headlineSmall),
            if (subtitle != null) ...[
              const SizedBox(height: AppSpacing.compact),
              Text(
                subtitle!,
                style: Theme.of(context)
                    .textTheme
                    .bodyMedium
                    ?.copyWith(color: context.appTokens.muted),
              ),
            ],
          ],
        ),
      );
}

class AppSurfaceCard extends StatelessWidget {
  const AppSurfaceCard({
    super.key,
    required this.child,
    this.padding,
    this.onTap,
    this.semanticLabel,
  });

  final Widget child;
  final EdgeInsetsGeometry? padding;
  final VoidCallback? onTap;
  final String? semanticLabel;

  @override
  Widget build(BuildContext context) {
    final content = Padding(padding: padding ?? EdgeInsets.zero, child: child);
    return Semantics(
      label: semanticLabel,
      button: onTap != null,
      child: Card(
        margin: const EdgeInsets.only(bottom: AppSpacing.compact),
        clipBehavior: Clip.antiAlias,
        child: onTap == null
            ? content
            : InkWell(
                onTap: onTap,
                child: ConstrainedBox(
                  constraints: const BoxConstraints(minHeight: 44),
                  child: content,
                ),
              ),
      ),
    );
  }
}

class AppStatusBadge extends StatelessWidget {
  const AppStatusBadge({
    super.key,
    required this.label,
    this.tone = AppStatusTone.neutral,
    this.icon,
  });

  final String label;
  final AppStatusTone tone;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    final tokens = context.appTokens;
    final (foreground, background) = switch (tone) {
      AppStatusTone.success => (tokens.success, tokens.successSoft),
      AppStatusTone.warning => (tokens.warning, tokens.warningSoft),
      AppStatusTone.danger => (tokens.danger, tokens.dangerSoft),
      AppStatusTone.neutral => (
          tokens.muted,
          tokens.border.withValues(alpha: .5)
        ),
    };
    return Semantics(
      label: label,
      child: ExcludeSemantics(
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
          decoration: BoxDecoration(
            color: background,
            borderRadius: BorderRadius.circular(999),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (icon != null) ...[
                Icon(icon, size: 16, color: foreground),
                const SizedBox(width: 6),
              ],
              Text(
                label,
                style: Theme.of(context)
                    .textTheme
                    .labelMedium
                    ?.copyWith(color: foreground, fontWeight: FontWeight.w800),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class AppNoticePanel extends StatelessWidget {
  const AppNoticePanel({
    super.key,
    required this.title,
    required this.message,
    this.tone = AppStatusTone.warning,
    this.icon = Icons.info_outline,
  });

  final String title;
  final String message;
  final AppStatusTone tone;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    final tokens = context.appTokens;
    final (foreground, background) = switch (tone) {
      AppStatusTone.success => (tokens.success, tokens.successSoft),
      AppStatusTone.danger => (tokens.danger, tokens.dangerSoft),
      AppStatusTone.warning => (tokens.warning, tokens.warningSoft),
      AppStatusTone.neutral => (tokens.muted, tokens.surface),
    };
    return Semantics(
      container: true,
      liveRegion: tone == AppStatusTone.danger,
      label: '$title，$message',
      child: ExcludeSemantics(
        child: Container(
          padding: const EdgeInsets.all(AppSpacing.regular),
          decoration: BoxDecoration(
            color: background,
            border: Border.all(color: foreground.withValues(alpha: .35)),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(icon, color: foreground),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title,
                        style: Theme.of(context).textTheme.titleSmall?.copyWith(
                            color: foreground, fontWeight: FontWeight.w800)),
                    const SizedBox(height: 4),
                    Text(message,
                        style: Theme.of(context)
                            .textTheme
                            .bodyMedium
                            ?.copyWith(color: foreground)),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class AppMetricTile extends StatelessWidget {
  const AppMetricTile({
    super.key,
    required this.label,
    required this.value,
    this.tone = AppStatusTone.neutral,
  });

  final String label;
  final String value;
  final AppStatusTone tone;

  @override
  Widget build(BuildContext context) => AppSurfaceCard(
        padding: const EdgeInsets.all(AppSpacing.regular),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            AppStatusBadge(label: label, tone: tone),
            const SizedBox(height: AppSpacing.compact),
            Text(value, style: Theme.of(context).textTheme.headlineSmall),
          ],
        ),
      );
}

class AppStatusPanel extends StatelessWidget {
  const AppStatusPanel({
    super.key,
    required this.icon,
    required this.title,
    this.message,
    this.loading = false,
    this.liveRegion = false,
    this.tone = AppStatusTone.neutral,
  });

  final IconData icon;
  final String title;
  final String? message;
  final bool loading;
  final bool liveRegion;
  final AppStatusTone tone;

  @override
  Widget build(BuildContext context) {
    final tokens = context.appTokens;
    final color = switch (tone) {
      AppStatusTone.success => tokens.success,
      AppStatusTone.warning => tokens.warning,
      AppStatusTone.danger => tokens.danger,
      AppStatusTone.neutral => Theme.of(context).colorScheme.primary,
    };
    final label = message == null ? title : '$title，$message';
    return Semantics(
      label: label,
      liveRegion: liveRegion,
      child: ExcludeSemantics(
        child: AppSurfaceCard(
          padding: const EdgeInsets.all(AppSpacing.generous),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (loading)
                SizedBox(
                  width: 28,
                  height: 28,
                  child:
                      CircularProgressIndicator(strokeWidth: 3, color: color),
                )
              else
                Icon(icon, size: 32, color: color),
              const SizedBox(height: AppSpacing.regular),
              Text(title, style: Theme.of(context).textTheme.titleMedium),
              if (message != null) ...[
                const SizedBox(height: AppSpacing.compact),
                Text(
                  message!,
                  textAlign: TextAlign.center,
                  style: Theme.of(context)
                      .textTheme
                      .bodyMedium
                      ?.copyWith(color: tokens.muted),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
