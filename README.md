# Palio Nav Offline Türkiye

Bu depo, Android araç multimedya cihazı için tek APK içinde Türkiye çevrimdışı haritaları bulunan bir navigasyon paketi üretir.

## Hedef

- Telefon gerekmez.
- SIM kart gerekmez.
- Navigasyon sırasında internet gerekmez.
- Multimedyanın dahili/harici GPS alıcısı kullanılır.
- Türkiye harita, yol, POI ve adres verileri APK içinde gelir.
- İlk çalıştırmada APK içindeki 7 Türkiye harita paketi uygulamanın veri klasörüne otomatik açılır.
- Sonraki açılışlarda doğrudan harita ekranı gelir.
- ARM 32-bit ve ARM 64-bit Android multimedya cihazları için tek APK üretilir.

## APK oluşturma

1. Bu klasörün içeriğini yeni bir GitHub deposuna yükleyin.
2. GitHub > Actions > **Build Palio Nav Offline APK** sayfasını açın.
3. **Run workflow** düğmesine basın.
4. İşlem tamamlanınca `PalioNav-Offline-Turkiye` artifact'ını indirin.
5. İçindeki `PalioNav-Offline-Turkiye.apk` dosyasını USB belleğe kopyalayın.

## Araçta kurulum

1. Multimedya Android ayarlarında bilinmeyen kaynaklardan APK kurulumuna izin verin.
2. USB'den `PalioNav-Offline-Turkiye.apk` dosyasına dokunun.
3. Android'in standart **Yükle** onayını verin.
4. Uygulamayı açın.
5. İlk çalıştırmada paket içindeki Türkiye haritaları hazırlanır. Bu aşamada internet kullanılmaz.
6. Android konum iznini bir kez onaylayın.
7. GPS konumu geldiğinde adres arayıp navigasyonu başlatabilirsiniz.

## Depolama

Türkiye'nin Eylül 2026 OsmAnd çevrimdışı bölge paketlerinin sıkıştırılmış toplamı yaklaşık 969 MB'dir. APK ve açılmış haritaların aynı anda cihazda bulunması nedeniyle en az 3 GB boş alan önerilir.

## Android sürümü

Bu builder güncel OsmAnd kaynağını kullanır. Güncel kaynak minSdk 24 ise Android 7.0 veya üzeri gerekir. Daha eski bir multimedya cihazında ayrı bir legacy branch gerekir.

## Harita bölgeleri

- Ege
- Karadeniz
- İç Anadolu
- Doğu Anadolu
- Marmara
- Akdeniz
- Güneydoğu Anadolu

## Güncelleme

Workflow tekrar çalıştırıldığında aynı OsmAnd indirme adlarından o gün sunulan güncel Türkiye paketleri alınır. Aynı paket adı ve aynı debug imza anahtarı kullanıldığı için sonraki APK, önceki Palio Nav kurulumunun üzerine güncelleme olarak kurulabilir.

## Lisans

Bu builder OsmAnd kaynağını derleme sırasında resmi `osmandapp` GitHub depolarından alır. OsmAnd kodu GPLv4 kapsamındadır; bazı görsel kaynakların ayrıca lisans koşulları vardır. OpenStreetMap verisi ODbL lisansına tabidir. Bu nedenle türev dağıtımlarda gerekli OsmAnd/OpenStreetMap atıfları korunmalıdır. Bu paket özel/sideload kullanım hedefiyle hazırlanmıştır.

## Builder v2 notu

OsmAnd manifestindeki launcher intent-filter satir girintileri degisse bile `scripts/patch_osmand.py` artik esnek desenle MapActivity launcher filtresini bulur. Palio Nav bootstrap activity launcher olarak atanir, OsmAnd ilk kullanim indirme ekrani kapatilir ve yatay ekran tercihi ilk acilista ayarlanir.

## v4 düzeltmesi

v1/v2 sürümlerindeki launcher `intent-filter` metnini değiştirme yöntemi kaldırıldı. v4, OsmAnd `MapActivity` launcher tanımına hiç dokunmaz. İlk çalıştırmada `MapActivity` güvenli şekilde yerel harita kurulum ekranına yönlendirir; 7 Türkiye haritası çıkarıldıktan sonra uygulama yeniden başlatılır. Bu yüzden upstream manifest girintisi/kategori sırası değişse bile önceki hata oluşmaz.


## v4 düzeltmesi

GitHub Actions içindeki harita indirme scripti artık `bash scripts/download_turkey_maps.sh android` ile çağrılır. Böylece GitHub'a ZIP üzerinden yükleme sırasında executable biti kaybolsa bile `Permission denied` hatası oluşmaz. Ayrıca ilk kurulum kodundaki gereksiz çift `closeEntry()` kaldırıldı.
