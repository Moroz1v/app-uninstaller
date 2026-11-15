Name:           app-uninstaller
Version:        1.0
Release:        4%{?dist}
Summary:        Графический менеджер удаления программ

License:        MIT
BuildArch:      noarch
Source0:        %{name}-%{version}.tar.gz

Requires:       python3
Requires:       python3-tkinter
Recommends:     python3-pillow

%description
Удобная графическая утилита для просмотра и удаления установленных
программ и пакетов (RPM, Flatpak, Snap, APT, Pacman, Zypper).

%prep
%setup -q

%install
mkdir -p %{buildroot}%{_bindir}
mkdir -p %{buildroot}%{_datadir}/applications
mkdir -p %{buildroot}%{_datadir}/icons/hicolor/128x128/apps
mkdir -p %{buildroot}%{_datadir}/pixmaps

install -m 0755 app-uninstaller %{buildroot}%{_bindir}/app-uninstaller
install -m 0644 app-uninstaller.desktop %{buildroot}%{_datadir}/applications/app-uninstaller.desktop
install -m 0644 app-uninstaller.png %{buildroot}%{_datadir}/icons/hicolor/128x128/apps/app-uninstaller.png
install -m 0644 app-uninstaller.png %{buildroot}%{_datadir}/pixmaps/app-uninstaller.png

%files
%{_bindir}/app-uninstaller
%{_datadir}/applications/app-uninstaller.desktop
%{_datadir}/icons/hicolor/128x128/apps/app-uninstaller.png
%{_datadir}/pixmaps/app-uninstaller.png

%changelog
* Sun Nov 15 2026 moroziv <moroziv@localhost> - 1.0-2
- Исправлен путь к иконке в .desktop для KDE Plasma и добавлена установка в pixmaps
