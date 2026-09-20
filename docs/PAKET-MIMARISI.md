# Palio Nav paket mimarisi

## Tek dosyalı kullanım

Son kullanıcı yalnızca `PalioNav-Offline-Turkiye.apk` dosyasını görür. Türkiye haritaları APK'nın `assets/palio_maps/` bölümünde yedi `.obf.zip` dosyası olarak taşınır.

İlk açılışta `PalioBootstrapActivity`:

1. APK içindeki map paketlerini listeler.
2. Her ZIP içindeki `.obf` dosyasını OsmAnd uygulama veri köküne çıkarır.
3. Yarım kalan dosyaları `.part` uzantısıyla tutar; dosya tamamlanınca atomik olarak gerçek adına çevirir.
4. Yedi bölgenin kurulumu tamamlanınca harita paket sürümünü SharedPreferences'a yazar.
5. Uygulamayı sessizce yeniden başlatır.
6. Sonraki açılışlarda kurulum ekranını atlayıp doğrudan `MapActivity` açar.

Bu yöntemle kullanıcının ayrıca klasör kopyalaması, harita indirmesi veya internet bağlantısı sağlaması gerekmez.
