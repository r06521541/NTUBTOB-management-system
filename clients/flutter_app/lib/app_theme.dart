import 'package:flutter/material.dart';

const appBrandNavy = Color(0xff102a43);

abstract final class AppSpacing {
  static const double compact = 8;
  static const double regular = 16;
  static const double generous = 24;
}

ThemeData appTheme(Brightness brightness) {
  final colors = ColorScheme.fromSeed(
    seedColor: appBrandNavy,
    brightness: brightness,
  );
  return ThemeData(
    useMaterial3: true,
    brightness: brightness,
    colorScheme: colors,
    scaffoldBackgroundColor: colors.surface,
    appBarTheme: AppBarTheme(
      centerTitle: false,
      backgroundColor: colors.surface,
      foregroundColor: colors.onSurface,
      surfaceTintColor: colors.surface,
    ),
    cardTheme: CardThemeData(
      elevation: 0,
      margin: EdgeInsets.zero,
      color: colors.surfaceContainerLow,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
    ),
    listTileTheme: ListTileThemeData(
      contentPadding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.regular,
        vertical: AppSpacing.compact,
      ),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
    ),
  );
}

class AppSurfaceCard extends StatelessWidget {
  const AppSurfaceCard({super.key, required this.child, this.padding});

  final Widget child;
  final EdgeInsetsGeometry? padding;

  @override
  Widget build(BuildContext context) => Card(
        margin: const EdgeInsets.only(bottom: AppSpacing.compact),
        child: Padding(
          padding: padding ?? EdgeInsets.zero,
          child: child,
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
  });

  final IconData icon;
  final String title;
  final String? message;
  final bool loading;
  final bool liveRegion;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
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
                  child: CircularProgressIndicator(
                    strokeWidth: 3,
                    color: colors.primary,
                  ),
                )
              else
                Icon(icon, size: 32, color: colors.primary),
              const SizedBox(height: AppSpacing.regular),
              Text(title, style: Theme.of(context).textTheme.titleMedium),
              if (message != null) ...[
                const SizedBox(height: AppSpacing.compact),
                Text(
                  message!,
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
