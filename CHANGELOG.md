# Değişiklik Geçmişi

Bu dosya, pipeline'da ve desteklenen şehirlerde yapılan önemli
değişiklikleri sürüm sürüm listeler.

## v1.8.0 - 2026-09-25

- 57 yeni şehir eklendi (toplam 63): her biri iki CSV (`ilce_nufus.csv`,
  `sege_2022_ilce.csv`) ve ince bir `adapter.py` ile. Kaynaklar, kapsanan
  ilçeler ve gerçek OSM ile ölçülen HVI kapsamı
  `docs/turkiye-ilce-yas-verisi-taramasi.md` kayıt sayfasında.
- **Kapsam denetimi**: `core/coverage.py` ve `validate_city.py --osm-coverage`
  bbox'taki yolların kaçının demografisi eşlenmiş bir mahalleye düştüğünü
  gerçek OSM özütüyle ölçer (eşik %60). Gerçek OSM'de denenen şehirlerin
  önemli bölümünde kapsam sıfırdı (ilçe adı ya da bbox uyuşmazlığı); HVI
  aşamasında boş dizide Jenks hatasıyla çöküyordu. Kapsamı %60'ın altında
  kalan 18 aday elendi.
- `tools/fit_city_bbox.py`: bbox'ı ilçenin tamamından ya da elle yazılmış
  koordinat karesinden değil, yoğun mahalle kümesinden çizer ve kapsamı
  ölçer.
- **Adapter düzeltmesi**: Merkez ilçe OSM'de "<İl> Merkez", CSV'de "Merkez"
  (ya da tersi) yazıldığında hiçbir mahalle eşleşmiyordu. Ortak modül artık
  bunu, yalnızca tek adaylı ve belirsizlik olmayan durumda eşler. Geçersiz
  OSM poligonları (ör. Kars) artık okumayı çökertmiyor.
- **Veri düzeltmeleri**: SEGE `KADEME`/`IL_ICI_SIRALAMA` alanları resmi PDF'e
  göre düzeltildi (Diyarbakır Yenişehir, Eskişehir Tepebaşı, Iğdır, Kırıkkale,
  Muğla Menteşe, Samsun İlkadım) ve `KADEME` skor eşiklerinden bir testle
  doğrulanıyor. İlçe çocuk oranı il ortalamasından inandırıcı olmayacak
  kadar sapan Kırklareli, Ağrı, Iğdır ve Karaman için il düzeyi 0-14/65+
  oranları kullanıldı.
- 47 şehir tek ilçe kapsar: nüfus yoğunluğu, yaşlı/çocuk oranı ve SEGE
  bileşenleri bu şehirlerde sabittir (bkz. README sınırlamalar).

## v1.7.0 - 2026-09-25

- Üç yeni şehir eklendi: **Antalya** (Muratpaşa + Konyaaltı + Kepez +
  Döşemealtı + Aksu), **Mersin** (Yenişehir + Akdeniz + Mezitli +
  Toroslar) ve **Adana** (Seyhan + Yüreğir + Çukurova + Sarıçam) - hepsi
  TÜİK-statik-CSV şablonuyla, aynı `mediterranean` OSM özütünü paylaşarak.
  İlçe nüfusları (ADNKS 2025) il toplamına tam eşit çıkana kadar
  doğrulandı (Adana'da iki kaynak arasındaki çelişki bu toplam kontrolüyle
  çözüldü); il düzeyi 0-14/65+ oranları üç yaş grubunun il toplamına
  eşitliği kontrol edilerek alındı; SEGE-2022 skorları resmi PDF'ten
  makine okumasıyla aktarıldı (elle yazılmadı). bbox'lar yoğun-mahalle
  yöntemiyle çizildi ve yalnızca CSV'deki ilçelerle kesiştiği gerçek OSM
  verisiyle doğrulandı; her üç şehirde `build_neighborhood_layer` gerçek
  veriyle sıfır NaN üretti. Landsat/HVI pipeline'ı bu şehirler için henüz
  çalıştırılmadı.
- Ortak TÜİK-şablonu mantığı `core/ilce_table_adapter.py`'ye alındı;
  Eskişehir ve Şanlıurfa adapter'ları ince sarmalayıcıya dönüştü (kod
  kopyası yerine). Şanlıurfa'nın çıktısı gerçek OSM verisiyle refactor
  öncesi/sonrası birebir aynı (`assert_frame_equal`). CSV'de olmayan bir
  ilçenin mahalleleri bbox'a girerse artık bir UYARI basılıyor (önceden o
  yollar sessizce HVI'dan dışlanıyordu).
- **Veri düzeltmesi**: Şanlıurfa'nın `COCUK_ORAN`'ı TÜİK'in 0-17 tanımlı
  %43,3'ü idi (projenin 0-14 tanımıyla uyumsuz); gerçek il 0-14 oranı
  %36,79 ile değiştirildi (yaşlı %4,51). Eskişehir'in oranları da
  gerçek 2025 değerlerine çekildi (çocuk %16,45 -> %16,11, yaşlı %13,05 ->
  %13,72). `docs/eskisehir/` altındaki yayınlanmış çıktı eski oranlarla
  üretilmişti, bir sonraki `--force` çalıştırmasında yenilenir.
- Gece ısı adası (MODIS) çıktıları da artık sürüm damgalı önbellek
  kullanıyor ve `--force` ile yeniden üretilebiliyor (#18).
- Yeni testler: ortak modülün davranışı (konumsal mahalle-ilçe eşlemesi,
  Türkçe isim normalizasyonu, yoğunluk formülü, eksik-ilçe uyarısı) ve
  repoyla gelen tüm şehir CSV'lerinin bütünlüğü (oran birimi, ilçe
  eşleşmesi, SEGE aralığı).

## v1.6.0 - 2026-09-23

- `landsat.max_cloud_cover` ve `landsat.max_scenes_per_tile` artık config
  doğrulamasında kontrol ediliyor - `max_scenes_per_tile: 0` gibi bir
  değer önceden sahne seçimini sessizce boşaltıp hatayı çok daha geç,
  anlaşılmaz bir noktada (mozaikleme aşamasında) veriyordu. (#15)
- Üretilen her HVI haritasının (`output/<sehir>_hvi_map.html` ve
  `docs/<sehir>/index.html`) yanına, o haritayı hangi şehir config'i,
  yıllar, Landsat sahneleri ve formül/önbellek sürümleriyle üretildiğini
  kaydeden bir `manifest.json`/`<sehir>_hvi_manifest.json` yazılıyor
  (bkz. README "Tekrar üretilebilirlik"). (#16)

## v1.5.0 - 2026-09-19

- Repo `izmir-heat-risk` -> `turkiye-heat-risk` olarak yeniden
  adlandırıldı - artık tek şehre özel olmayan bir isim (üçüncü şehir bu
  sürümde eklendi). README/CI workflow'undaki hardcode repo adı
  referansları (badge URL'i, docker tag'i, klonlama komutu) güncellendi.
- Üçüncü şehir olarak **Şanlıurfa** eklendi (Haliliye + Eyyübiye +
  Karaköprü çekirdeği), Eskişehir'in TÜİK-statik-CSV şablonuyla - CKAN
  portalı olmayan HERHANGİ bir Türkiye şehri için şablonun tekrar
  kullanılabilir olduğunu kanıtlar. Nüfus (ADNKS 2025), yaşlı oranı
  (TÜİK 2025) ve SEGE-2022 skorları resmi kaynaklardan (bkz.
  `src/cities/sanliurfa/adapter.py` docstring'i - kaynaklar ve bilinen
  bir kapsam sınırlaması: il düzeyinde 0-14 yaş yayını bulunamadığı için
  TÜİK'in kendi 0-17 "çocuk nüfus" tanımı kullanıldı). bbox, idari ilçe
  sınırları yerine (Harran ovasına uzanan geniş kırsal alanı dışarıda
  bırakmak için) gerçek kentsel mahalle kümesi baz alınarak belirlendi.

## v1.4.0 - 2026-09-18

- Bozuk/eksik alanlı `config.yaml` dosyaları için anlaşılır hata
  mesajları üretildi (`core/city_config.py`) - önceden belirsiz bir
  `KeyError`/`TypeError` ile patlıyordu.

## v1.3.0 - 2026-09-17

- OSM centroid hesaplamasındaki gerçek bir CRS hatası düzeltildi:
  coğrafi (derece) CRS'te centroid almak büyük/simetrik olmayan
  poligonlarda merkezi sistematik kaydırıyordu (`osm_amenities.py`,
  `load_health_points`/`load_building_centroids`).
  Landsat sahne seçimine çoklu-sahne medyan kompozit eklendi (tek
  sahneye kıyasla tek-günlük anomalilerin etkisini azaltır).
  Dockerfile'a rasterio için eksik `libexpat1`/`libgomp1` sistem
  kütüphaneleri eklendi - CI'a eklenen yeni `docker` job'ının build
  sırasında yakaladığı ilk gerçek bug.
  `validate_city.py`'a adapter/EPSG doğrulaması eklendi, test kapsamı
  genişletildi.

## v1.2.0 - 2026-09-16

- CI eklendi (GitHub Actions, `pytest` job'ı). `map_builder.py` için
  test kapsamı genişletildi. Bağımlılıklara üst sınır (`requirements.txt`)
  ve İzmir'in eski `aegean-latest.osm.pbf` dosya adı için tekilleştirilmiş
  bir geriye dönük uyumluluk yolu eklendi.

## v1.1.0 - 2026-09-14

- `core/roads.py`, `core/text_utils.py` ve `core/osm_amenities.py` hiç
  test kapsamında değildi; ortak (yıl bazlı değil) min-max risk skoru
  ölçeklemesi, Türkçe karakter normalizasyonu ve OSM `other_tags`
  ayrıştırması için testler eklendi.

## v1.0.0 - 2026-09-12

İlk sürüm: uçtan uca çalışan pipeline (Landsat LST/NDVI -> OSM yol ağı ->
9 bileşenli geometrik ortalama Isı Hassasiyet Endeksi -> interaktif Folium
haritası), şehir bazlı mimari (`src/core/` şehirden bağımsız,
`src/cities/<sehir>/` izole), iki referans şehir (İzmir: CKAN tabanlı
adapter; Eskişehir: TÜİK-statik-CSV şablonu), sürüm damgalı önbellek
(`core/cache.py`), iki farklı harita çıktısı (çevrimdışı tek dosya +
GitHub Pages için fetch tabanlı bölünmüş sürüm), Landsat QA_PIXEL piksel
düzeyinde bulut maskesi ve ilk test paketi.
