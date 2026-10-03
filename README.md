# Kentsel Isı Adası ve Isı Hassasiyet Endeksi (HVI)

[![Testler](https://github.com/Ayberkrk/turkiye-heat-risk/actions/workflows/tests.yml/badge.svg)](https://github.com/Ayberkrk/turkiye-heat-risk/actions/workflows/tests.yml)
[![lisans](https://img.shields.io/badge/lisans-MIT-blue)](LICENSE)
[![sürüm](https://img.shields.io/github/v/tag/Ayberkrk/turkiye-heat-risk?label=s%C3%BCr%C3%BCm&color=informational)](https://github.com/Ayberkrk/turkiye-heat-risk/releases)

Sürüm geçmişi için [CHANGELOG.md](CHANGELOG.md), atıf için
[CITATION.cff](CITATION.cff) dosyalarına bakın.

## English summary

An open-data, reproducible urban heat risk pipeline. It combines Landsat
land surface temperature (LST), the OpenStreetMap road network, and
demographic data into a street-level, explainable Heat Vulnerability Index
(HVI): Landsat LST/NDVI, a road-to-temperature spatial join, and an index
that groups nine components into Hazard (surface temperature), Exposure
(population and built-up density) and Vulnerability (elderly/child share,
socioeconomic development, distance to health care and green space, tree
canopy). Components are averaged within a group and the three groups are
combined by geometric mean, so each group carries one third of the index
regardless of how many components it holds. Categories use Jenks natural
breaks shared across years. Live maps:
<https://ayberkrk.github.io/turkiye-heat-risk/>. The index is a
prioritisation tool; it has not been validated against health outcomes. The architecture is city-agnostic -
`src/core/` never changes when a new city is added; 70 cities are supported
today (Izmir, Eskişehir, Şanlıurfa, Antalya, Mersin, Adana and 64 more, listed
with their data sources and measured OSM coverage in
[the register](docs/turkiye-ilce-yas-verisi-taramasi.md); see
[CONTRIBUTING.md](CONTRIBUTING.md) to add another). Cities that cover a single
district have constant demographic components, so their maps show heat and
green cover, not demographic vulnerability.

Quick start (produces a single-file interactive HTML map):

```bash
python pipeline.py --city izmir --years 2020 2026 --main-year 2026 --open
```

The rest of this README - methodology, findings, setup, project layout,
known limitations - is in Turkish (this is an Izmir/Türkiye-focused
project). Machine translation works well if you want the full detail; the
summary above and the code/docstrings should be enough to navigate the
repository.

---

Açık verilerle çalışan, tekrar üretilebilir bir kentsel ısı riski analiz hattı.
Landsat yüzey sıcaklığı, OpenStreetMap yol ağı ve demografik verileri
birleştirerek ısı riskini sokak ölçeğinde haritalar. Şehirden bağımsız bir
mimariye sahiptir; şu an 70 şehir destekleniyor (İzmir, Eskişehir, Şanlıurfa,
Antalya, Mersin, Adana ve 64 şehir daha; kaynakları ve gerçek OSM ile ölçülen
kapsamları [kayıt sayfasında](docs/turkiye-ilce-yas-verisi-taramasi.md)).
Yeni bir şehir eklemek `src/core/` içindeki hiçbir dosyayı değiştirmeden
mümkündür (bkz. [CONTRIBUTING.md](CONTRIBUTING.md)).

**Canlı harita:** <https://ayberkrk.github.io/turkiye-heat-risk/> (GitHub
Pages'te barındırılan, veri talep üzerine yüklenen küçük sürüm; kaynağı
`docs/`). Tamamen çevrimdışı, tek dosyalık sürüm (~60 MB, GitHub'ın 50 MB
uyarı/100 MB ret sınırını aştığı için depoda tutulmuyor) aşağıdaki komutla
birkaç dakikada yerelde üretilir:

```bash
python pipeline.py --city izmir --years 2020 2026 --main-year 2026 --open
```

![İzmir HVI interaktif haritası: yol ağı Isı Hassasiyet Endeksi'ne göre turuncudan bordoya renklendirilmiş, sağ üstte katman kontrolü, sol altta yıl seçici ve gösterge](assets/screenshots/harita-genel.png)

## İçindekiler

- [Ne yapıyor?](#ne-yapıyor)
- [Başka bir şehre/bölgeye uyarlama](#başka-bir-şehrebölgeye-uyarlama)
- [Metodoloji](#metodoloji)
- [Çok yıllı duyarlılık ve müdahale analizi](#çok-yıllı-duyarlılık-ve-müdahale-analizi)
- [2020 → 2026: Bulgular](#2020--2026-bulgular)
- [Kurulum ve çalıştırma](#kurulum-ve-çalıştırma)
- [Proje yapısı](#proje-yapısı)
- [Bilinen sınırlamalar](#bilinen-sınırlamalar)

## Ne yapıyor?

1. **Uydu verisi** - Landsat 8/9 (Microsoft Planetary Computer) üzerinden
   İzmir büyükşehir alanını kaplayan en az bulutlu yaz sahnelerini indirir.
2. **Yüzey sıcaklığı (LST) ve NDVI** - termal banttan gerçek yüzey
   sıcaklığını (°C), kırmızı/yakın-kızılötesi banttan bitki örtüsü
   yoğunluğunu hesaplar; sahneleri tek bir kesintisiz mozaikte birleştirir.
3. **Yol ağı ↔ sıcaklık eşlemesi** - OpenStreetMap'ten çekilen ~44.000 yol
   segmentinin her birine, 10 metrelik bir tampon içindeki ortalama LST'yi
   atar ve 0-100 arası bir "risk skoru"na çevirir.
4. **Isı Hassasiyet Endeksi (HVI)** - sıcaklık, ağaç örtüsü, nüfus
   yoğunluğu, yaşlı/çocuk nüfus oranı, hastane/eczaneye uzaklık, yeşil
   alana uzaklık ve yapılaşma yoğunluğunu tek bir 0-100 skorda birleştirir;
   "burası hem sıcak hem kalabalık/yaşlı/çocuk nüfuslu hem de ağaçsız ve
   sağlık hizmetine uzak, yani gerçek risk burada" sorusuna cevap verir.
   Her bileşenin kendi değeri de ayrı ayrı saklanır - nihai skor tek başına
   değil, onu oluşturan etkenlerle birlikte görünür (bkz. Metodoloji).
5. **İnteraktif harita** - kategori bazlı aç/kapa katmanları, 2020/2026
   yıl seçici ve her yola tıklandığında skoru oluşturan tüm bileşenleri
   gösteren bir tooltip içeren, tarayıcıda tek dosya olarak açılabilen bir
   Folium/Leaflet haritası üretir.
6. **Çok yıllı analiz paketi (isteğe bağlı)** - üç veya daha fazla yılı
   ERA5-Land hava anomalisiyle karşılaştırır; HVI ağırlıklarını ve yol
   tamponlarını değiştirerek sıralama kararlılığını ölçer; ağaçlandırma ve
   gölgeleme what-if senaryolarını ayrı bir haritada gösterir.

## Başka bir şehre/bölgeye uyarlama

Proje artık şehir bazlı bir mimariye sahip: `src/core/` altındaki kod
tamamen şehirden bağımsızdır, İzmir'e özel her şey
`src/cities/izmir/config.yaml` ve `src/cities/izmir/adapter.py` içinde
izole edilmiştir. Yeni bir şehir eklemek `src/core/` içindeki
sabitleri değiştirmeyi **gerektirmez** - adım adım süreç için
[CONTRIBUTING.md](CONTRIBUTING.md)'ye bakın. Özetle:

**1. `src/cities/<sehir>/config.yaml` oluştur**
`bbox` (derece cinsinden [batı, güney, doğu, kuzey]), hedef UTM `crs`'i,
OSM `.osm.pbf` özüt URL'i ([openstreetmap.fr](https://download.openstreetmap.fr/extracts/)
veya [Geofabrik](https://download.geofabrik.de/)), `admin_level_ilce` /
`admin_level_mahalle` (bu etiket ülkeden ülkeye değişir - kendi bölgende
`osm_gdf['admin_level'].unique()` ile önceden doğrula) buraya yazılır.

**2. Bir demografi "adapter"ı yaz (en fazla emek isteyen adım)**
İki referans örnek farklı veri kaynağı senaryolarını gösterir:
  - `src/cities/izmir/adapter.py`: belediyenin kendi CKAN tabanlı açık veri
    portalı varsa (`acikveri.bizizmir.com`), mahalle seviyesinde nüfus/yaş.
  - `src/cities/eskisehir/adapter.py`: böyle bir portal YOKSA, TÜİK'in
    herkese açık ilçe seviyesindeki ADNKS yayınlarını statik CSV olarak
    kullanan şablon - kendi CKAN'ı olmayan başka bir Türkiye şehri için
    neredeyse değişiklik yapmadan uyarlanabilir. Ortak mantık
    `src/core/ilce_table_adapter.py`'de. Yeni şehir eklerken aynı yıl için
    ilçe düzeyinde 0-14, 15-64 ve 65+ sayımlarını doğrula; il oranlarını
    ilçe satırına yedek olarak yazma. Depodaki bazı eski şehir kayıtlarında
    il oranı kullanımı vardır; bunlar kayıt sayfasında ayrıca işaretlenmiştir.
    `tools/fit_city_bbox.py` bbox'ı yoğun mahalle kümesinden çizer ve gerçek
    OSM ile HVI kapsamını ölçer (eşik %60, bkz. `validate_city.py
    --osm-coverage`). Merkez ilçe OSM'de "<İl> Merkez", CSV'de "Merkez"
    (ya da tersi) yazılmış olabilir; `core/ilce_table_adapter.py` bunu eşler.

Her iki örnek de `fetch_population_data()` / `build_neighborhood_layer()`
arayüzünü uygular. Yeni bir şehir için aynı arayüzü uygulayan kendi
adapter'ını `src/cities/<sehir>/adapter.py` altında yaz:
  - Mahalle/idari sınır poligonlarını OSM'den çekmeye devam edebilirsin.
  - Nüfus yoğunluğu, yaşlı ve çocuk nüfus oranı verisini yerel istatistik
    kurumundan (TÜİK, Eurostat, US Census vb.) veya belediyenin kendi açık
    veri portalından CSV/JSON olarak al.
  - Mahalle-ilçe eşlemesi her iki adapter'da da **isme göre değil konumsal
    sorguyla** (`sjoin`, centroid içinde mi) yapılıyor - aynı isimli
    mahallelerin yanlış ilçeyle eşleşmesini önlüyor. Bu yaklaşımı koru,
    hangi ülkede olursan ol işe yarar.

**3. Doğrula ve çalıştır**
```bash
python validate_city.py <sehir>
python pipeline.py --city <sehir> --years <yıllar>
```
`validate_city.py`, config.yaml'ın gerekli alanları içerdiğini, bbox'ın
geçerli olduğunu, adapter'ın import edilebildiğini ve veri kaynağı
URL'lerinin erişilebilir olduğunu indirmeden önce kontrol eder.

**4. HVI bileşenlerini değiştir**
`src/core/hvi.py` içindeki `COMPONENT_GROUPS` hangi bileşenin hangi gruba
(tehlike, maruziyet, kırılganlık) girdiğini tanımlar. Yeni bir bileşen
eklemek için sütununu `robust_normalize_0_1` ile üret, ilgili gruba ekle ve
`HVI_FORMULA_VERSION`'ı artır.

## Metodoloji

### Yüzey sıcaklığı (LST)

Landsat Collection 2 Level-2 ürünleri, termal bandı laboratuvarda zaten
Kelvin cinsinden yüzey sıcaklığına kalibre eder. Tek gereken ölçek dönüşümü:

```
LST(K) = piksel_değeri × 0.00341802 + 149.0
LST(°C) = LST(K) - 273.15
```

Sahneler varsayılan olarak 1 Temmuz - 31 Ağustos arasında aranır. Sıcak
sezon şehirden şehre değiştiği için pencere `config.yaml`'ın `landsat`
bölümünden ayarlanabilir (`season_start: "06-15"`, `season_end: "09-15"`).
Yıllar arası karşılaştırmada aynı pencere kullanılmalıdır; pencereyi
değiştirdikten sonra `--force` ile sahneleri yeniden seçtirin.

**Termal bandın gerçek çözünürlüğü 100 m'dir.** Landsat 8/9 TIRS algılayıcısı
yüzey sıcaklığını yaklaşık 100 m'de ölçer; USGS ürünü 30 m ızgaraya yeniden
örnekler. Bu yüzden haritadaki sıcaklık yol segmenti başına raporlansa da
birbirine 100 m'den yakın sokaklar büyük ölçüde aynı ölçümü paylaşır:
harita mahalle içi sıcak bölgeleri ayırt eder, tek tek komşu sokakları
değil. NDVI (30 m) bu sınırlamayı taşımaz.

Bulutlar kızılötesiyi bozduğu için her sahne aranırken bulut oranı %30'un
altında tutulur ve her uydu karosu (path/row) için mevcut en temiz
`max_scenes_per_tile` (varsayılan 3, `config.yaml`'ın `landsat` bölümünden
ayarlanır) kadar tarih seçilir.

Sahne düzeyindeki düşük bulut oranı tek başına yeterli değil: toplam bulut
oranı düşük bir sahnede bile bulutun küçük bir kısmı doğrudan çalışma
alanının üzerine düşebilir. Bu yüzden `QA_PIXEL` bandı da indirilip LST ve
NDVI hesaplanmadan önce, sahnenin kendi piksel ızgarasında (mozaikleme ve
yeniden izdüşürmeden önce) piksel düzeyinde bir bulut maskesi uygulanır:
fill, dilated cloud, cirrus, cloud, cloud shadow ve snow bayraklarından
herhangi biri taşıyan pikseller `NaN`/nodata yapılır (`core/raster.py`,
`qa_invalid_mask`).

**Çoklu sahne kompoziti:** tek bir sahne seçmek yerine, her karo için
seçilen `max_scenes_per_tile` kadar sahnenin LST/NDVI'si ayrı ayrı
hesaplanıp (QA maskesi her biri kendi ızgarasında uygulanmış olarak) piksel
bazlı **medyanı** alınır (`core/raster.py`, `composite_scene_arrays`).
Aynı karonun farklı tarihli sahneleri aynı piksel ızgarasında gelmediği
için (başlangıç noktası yüzlerce metre kayabilir) sahneler önce karonun
ortak ızgarasına oturtulur (`tile_grid`), sonra medyanı alınır.
Medyan, ortalamadan daha dayanıklıdır - aykırı tek bir bulutlu/anormal
günün sonucu domine etmesini engeller. Bu, aşağıdaki "Metodolojik uyarı"da
bahsedilen tek-sahne kaynaklı gürültüyü azaltır (aynı yaklaşım, gece ısı
adası katmanı için `core/night_lst.py`'de zaten kullanılıyordu).
`max_scenes_per_tile: 1` ile eski tek-sahne davranışına dönülebilir.

**UTM dilim sınırındaki şehirler:** USGS her Landsat sahnesini kendi
merkezine en yakın UTM dilimine işler. Bir şehrin bbox'ı iki komşu path/row
karosunun kesiştiği ve bu karoların farklı UTM dilimlerine düştüğü bir
noktaya denk gelirse (Eskişehir'de yaşandı: 4 karodan 3'ü UTM 36N/EPSG:32636,
biri UTM 35N/EPSG:32635), mozaikleme öncesi tüm sahneler `config.crs`'e
yeniden izdüşürülür (`core/raster.py`, `reproject_to_crs`) - aksi halde
`stream_mosaic` farklı dilimdeki sahneyi (aynı sayısal koordinatlar farklı
coğrafi konuma karşılık geldiği için) yanlış yere yapıştırır ve o bölgede
neredeyse hiç geçerli piksel kalmaz.

### Yol ↔ sıcaklık eşlemesi (spatial join)

Yollar çizgi geometrisi olduğu için doğrudan piksel ortalaması alınamaz;
her yola 10 metrelik bir tampon (buffer) verilip bu koridorun içine düşen
piksellerin **ortalaması** (aykırı değerlere karşı `mean`, `max`'tan daha
dayanıklı) `rasterstats.zonal_stats` ile hesaplanır. Sonuç, tüm yolların
ortak min-max aralığına göre 0-100'e normalize edilerek "risk skoru"na
çevrilir.

### Isı Hassasiyet Endeksi (HVI): çok bileşenli ve açıklanabilir

HVI, dokuz bileşeni üç grupta toplar ve grupları geometrik ortalamayla
birleştirir:

```
Grup skoru = grubun bileşenlerinin aritmetik ortalaması
HVI        = geometrik_ortalama(Tehlike, Maruziyet, Kırılganlık) × 100
```

| Grup | Bileşen | Ne ölçer | Kaynak |
|---|---|---|---|
| Tehlike | Yüzey sıcaklığı | LST risk skoru (yıl bazlı) | Landsat termal bant |
| Maruziyet | Nüfus yoğunluğu | Kişi/km² | Şehir adapter'ı (belediye açık verisi ya da TÜİK) |
| Maruziyet | Yapılaşma yoğunluğu | Yolun 150 m çevresindeki bina yoğunluğu | OSM bina (`building`) katmanı |
| Kırılganlık | Yaşlı oranı | 65+ nüfus oranı (ilçe) | Şehir adapter'ı |
| Kırılganlık | Çocuk oranı | 0-14 nüfus oranı (ilçe) | Şehir adapter'ı |
| Kırılganlık | Sosyoekonomik gelişmişlik | İlçe bazlı SEGE-2022 skorunun tersi | T.C. Sanayi ve Teknoloji Bakanlığı, resmi SEGE-2022 raporu |
| Kırılganlık | Sağlık erişimi | En yakın hastane/klinik/eczaneye uzaklık | OSM (`amenity=hospital/clinic/pharmacy`) |
| Kırılganlık | Yeşil alan erişimi | En yakın park/orman/çayır poligonuna uzaklık | OSM (`leisure=park`, `landuse=forest` vb.) |
| Kırılganlık | Ağaç örtüsü | Yol tamponundaki ortalama NDVI'nin tersi | Landsat NDVI |

**Neden gruplu?** v1.x'te dokuz bileşenin düz geometrik ortalaması
alınıyordu. Orada bileşen sayısı gizli bir ağırlıktı: yedi kırılganlık
bileşenine karşı tek bir sıcaklık bileşeni, bir *ısı* endeksinde sıcaklığın
payını 1/9'a indiriyordu. Ayrıca birbiriyle ilişkili bileşenler (NDVI ile
LST, bina ile nüfus yoğunluğu) aynı sinyali iki kez sayıyordu. Gruplu yapıda
her grubun payı, içindeki bileşen sayısından bağımsız olarak 1/3'tür. Bu,
afet riski literatüründeki Tehlike × Maruziyet × Kırılganlık çerçevesiyle
aynı sıralamayı verir (üç grubun geometrik ortalaması, çarpımlarının küp
köküdür).

**Grup içi ve gruplar arası fark:** aynı gruptaki bileşenler birbirini
telafi edebilir (yaşlı oranı düşük ama sağlık erişimi kötü bir yol orta
kırılganlıkta çıkar), bu yüzden grup içinde aritmetik ortalama kullanılır.
Gruplar ise birbirini telafi edemez: sıcak olmayan ya da kimsenin
yaşamadığı bir yolda kırılganlık ne kadar yüksek olursa olsun risk düşük
kalmalıdır, bu yüzden gruplar arasında geometrik ortalama kullanılır.

**Grup skorları birleştirilmeden önce yeniden ölçeklenir.** Ortalama almak
yayılımı daraltır: altı bileşenli kırılganlık grubunda bileşenler birbirini
götürür (yaşlı ve çocuk oranı ters ilişkilidir) ve grup skoru dar bir bantta
kalır. Dar bantta kalan bir grup, ağırlığı 1/3 olsa bile sıralamayı
etkilemez; İzmir'de bu adım olmadan kırılganlığın HVI ile sıra korelasyonu
0,00 çıkıyordu. Bu yüzden üç grup skoru da tüm yılların ortak dağılımına
göre 0-1'e çekilir, sonra birleştirilir. Bu adım etkileri eşitlemez (bkz.
"Bulgular"daki ölçüm) ama hiçbir grubun dekoratif kalmasını önler.

**Ölçekleme aykırı değere dayanıklı:** her bileşen min-max yerine %2-%98
yüzdelik aralığına göre 0-1'e çekilir, dışarıda kalan değerler 0 ya da 1'e
kırpılır. Min-max'ta tek bir uç yol (ör. en yakın hastaneye 40 km uzaktaki
bir kırsal segment) geri kalan tüm yolları ölçeğin dar bir bandına
sıkıştırıyordu.

**Ayırt etmeyen bileşenler endekse alınmaz:** bir bileşen şehrin tüm
yollarında aynı değeri alıyorsa (tek ilçeli şehirlerde ilçe düzeyindeki
demografik bileşenler) grup ortalamasına girmez; aksi halde sabit bir 0,
grubun diğer üyelerinin etkisini seyreltirdi. Pipeline bu durumda hangi
bileşenleri dışarıda bıraktığını ekrana yazar.

Geometrik ortalamanın bir yan etkisi var: 0, "hiç risk yok" değil "veri
kümesindeki en düşük değer" demektir ve tek başına tüm skoru sıfırlar. Bu
yüzden grup skorları birleştirilmeden önce `[0,05, 1]` aralığına
ölçeklenir. Böylece "bir grup düşükse toplam risk de düşer" davranışı
korunur ama tek bir grup skoru tamamen ele geçiremez.

**Bu seçimler bir yargıdır, ölçüm değil.** Grup paylarının eşit olması ve
bileşenlerin hangi gruba girdiği, sağlık sonuçlarıyla kalibre edilmiş
değildir. `analyze_pipeline.py` farklı ağırlık profilleriyle sıralamanın ne
kadar değiştiğini raporlar (bkz. "Çok yıllı duyarlılık ve müdahale
analizi"); endeksin kendisi hastane başvurusu ya da ölüm verisiyle henüz
doğrulanmamıştır (bkz. "Bilinen sınırlamalar").

**İki yıl karşılaştırılabilir:** HVI yüzdesi ve Jenks kategori sınırları
her yıl ayrı ayrı değil, tüm yılların **ortak** dağılımından hesaplanır.
Her yıl kendi içinde 0-100'e ölçeklenseydi tanım gereği her yılın en kötü
yolu %100 çıkar ve "2026'da risk arttı" demek mümkün olmazdı. LST risk
skorunda uygulanan ortak ölçek mantığı HVI'de de sürdürülür.

**Etiketler yüzdelik dilime göre:** haritadaki "yüksek / orta / çok yakın"
gibi etiketler eşit genişlikte aralıklara değil, sıralamaya (yüzdelik
dilim) göre üretilir. Eşit aralık kullanıldığında birkaç uç değer tüm
skalayı ele geçiriyor ve yolların %91'i "hastaneye çok yakın" çıkıyordu;
şimdi her etiket yolların yaklaşık beşte birine denk geliyor.

**Açıklanabilirlik:** nihai HVI skorunun yanında her bileşenin kendi
normalize değeri ve üç grup skoru da GeoJSON'a yazılır (`hazard_norm_<yıl>`,
`exposure_norm`, `sensitivity_*_norm`, `group_*_<yıl>` sütunları) ve haritadaki tooltip'te
"Sıcaklık: yüksek, Ağaç örtüsü: çok düşük, Hastaneye uzaklık: uzak..."
şeklinde okunabilir etiketlere çevrilir - bir yolun HVI'sinin neden
yüksek/düşük olduğu haritadan doğrudan görülebilir.

Yaş dağılımı verisi sadece **ilçe** seviyesinde mevcut olduğu için, bir
ilçenin yaşlı/çocuk oranı o ilçenin tüm mahallelerine aynı şekilde
uygulanır (downscaling) - ilçe-içi ince farkları gözden kaçırır ama kaba
veriyle çalışırken standart ve dürüst bir yaklaşımdır.

**Sosyoekonomik bileşen:** İzmir B.Ş.B. açık veri portalında ve TÜİK'te
mahalle/ilçe seviyesinde güncel, güvenilir bir eğitim/gelir göstergesi
bulunamadı; onun yerine T.C. Sanayi ve Teknoloji Bakanlığı'nın resmi
**"İlçelerin Sosyo-Ekonomik Gelişmişlik Sıralaması Araştırması
(SEGE-2022)"** raporundaki ilçe bazlı gelişmişlik skoru kullanıldı - bu,
81 ilin tüm ilçelerini 56 değişkenle (demografi, istihdam, eğitim, sağlık,
finans, rekabetçilik, yaşam kalitesi) kapsayan, kamuya açık, tek seferlik
yayımlanmış resmi bir araştırma. Bu yüzden CKAN'dan indirilmek yerine
`src/cities/izmir/sege_2022_ilce.csv` olarak küçük bir referans dosyası
halinde repoya dahil edildi (bkz. `cities/izmir/adapter.py`). Bu bileşen
**isteğe bağlıdır** - başka bir şehrin adapter'ı bu veriyi sağlamazsa HVI
kalan bileşenlerle hesaplanmaya devam eder.

**Bu HVI, kapsamlı bir sağlık veya sosyoekonomik kırılganlık modeli değil;
mevcut açık verilerle oluşturulmuş, çok bileşenli bir önceliklendirme
endeksidir.**

### Kategorilere ayırma: neden Jenks doğal kırılım?

HVI skorları üç grup skorunun geometrik ortalaması olduğu için dağılım çarpık -
çoğu yol düşük skorda toplanır, az sayıda yol çok yüksek skora sıçrar.
İlk denemede `pd.qcut` (her kategoriye eşit sayıda yol) kullanıldı ama bu,
verideki gerçek yapıyı değil, zorla eşit dağıtılmış bir bölünmeyi
yansıtıyordu. **Jenks doğal kırılım** (`jenkspy`) bunun yerine grup-içi
varyansı minimize edip gruplar-arası varyansı maksimize eden sınırları
matematiksel olarak bulur - yani "doğada var olan" kümelenme noktalarını
tespit eder, kategorilere zorla eşit yol sayısı dağıtmaz. Jenks sınırları
2020 ve 2026 için ayrı ayrı değil, iki yılın **ortak** dağılımından bir
kez hesaplanır; böylece "Kritik" her iki yılda aynı eşiği ifade eder ve
bir yolun yıllar arasında kategori değiştirmesi gerçek bir değişimi
gösterir.

(Bu, tooltip'teki "yüksek / çok yakın" gibi bileşen etiketlerinden ayrı
bir karardır: **kategoriler** Jenks ile, **etiketler** yüzdelik dilimle
üretilir. Kategorilerde amaç verideki gerçek kümelenmeyi bulmak,
etiketlerde ise okuyucuya "bu yol diğerlerine göre nerede duruyor"
sorusunun cevabını vermek.)

### Zaman serisi: 2020 vs 2026 neden "ortak" normalize ediliyor?

Risk skorunu her yıl kendi min-max'ıyla normalize edersen, "2020'de 45°C"
ile "2026'da 45°C" farklı skorlara denk gelir - karşılaştırma anlamsızlaşır.
Bunun yerine iki yılın LST değerleri birleştirilip **tek bir ortak
min-max aralığı** bulunur, her iki yıl da bu aynı cetvelle ölçülür.

### Gece ısı adası (isteğe bağlı, `--night-lst`)

Landsat'ın termal bandı gündüz geçişi için tasarlanmıştır; gece ısı adası
etkisi (şehir merkezlerinin kırsala göre geceleri daha yavaş soğuması,
genelde gündüzden daha güçlü hissedilen bir etki) bu veri setinde yoktu.
`--night-lst` bayrağı, aynı Planetary Computer altyapısından MODIS'in
"LST_Night_1km" ürününü çeker (yazın tüm 8 günlük kompozitlerinin
piksel bazlı ortalaması, tek bir bulutlu gecenin sonucu domine etmesini
önlemek için). MODIS 1 km çözünürlükte olduğu için (Landsat'ın 30 m'sinin
aksine) bu katman yol segmenti değil **mahalle** ölçeğinde sunulur ve
HVI skoruna dahil edilmez - haritada ayrı, varsayılan olarak kapalı bir
katmandır.

## Çok yıllı duyarlılık ve müdahale analizi

Ana hattın haritası iki ya da daha fazla yılı karşılaştırabilir. Daha uzun
dönem, hava düzeltmesi ve karar senaryoları için en az üç yılın ana pipeline
çıktıları hazır olduktan sonra ikinci komutu çalıştırın. Örnek:

```bash
python pipeline.py --city izmir --years 2013 2016 2019 2022 2024 2026 --main-year 2026
python analyze_pipeline.py --city izmir --years 2013 2016 2019 2022 2024 2026 --main-year 2026
```

Analiz belirtilen yılların hazır raster ve yol/HVI çıktısını okur; uydu
indirme ve ana hattı yeniden çalıştırmaz. Landsat 8/9 arşivinin 2013'ten
başlayan yılları kullanılabilir. Hava kaynağı
[Open-Meteo tarihsel hava API'sindeki ERA5-Land yeniden analizidir](https://open-meteo.com/en/docs/historical-weather-api).
ERA5-Land 1950'den beri tutarlı tarihsel sıcaklık serisi sunar. Çalışma
alanında 12 örnek konum kullanılır.

Hava düzeltmesi, seçili Landsat sahne günlerinin 2 m hava sıcaklığı
ortalamasını aynı takvim günlerinin ±7 gün penceresindeki 1991-2020
normalinden çıkarır. Bu anomali, yolun Landsat LST'sinden `β × anomali`
olarak düşülür. `β` varsayımsal eşleştirme katsayısıdır; `β=0`, `0.5` ve
`1` sonuçları raporlanır. ERA5-Land hava sıcaklığı ile Landsat yüzey
sıcaklığı farklı ölçümlerdir; düzeltilmiş değer bir hassasiyet tahminidir,
istasyon ölçümüyle doğrulanmış LST değildir. Yıllık doğrusal eğim
betimleyici bir özettir, nedensel iklim etkisi tahmini değildir.

HVI duyarlılık tablosu mevcut bileşenleri üç açık ağırlık profiliyle
hesaplar: eşit, ısı öncelikli ve eşitlik öncelikli. Mekânsal duyarlılık
analizi varsayılan olarak 10, 30 ve 50 m yol tamponlarında LST/NDVI
örneklerini yeniden alır. Her seçenek için son yılın ilk %10 riskli yol
kümesinin varsayılan profile göre örtüşmesi ve Spearman sıra korelasyonu
raporlanır. Böylece farklı puan aralıklarından kaynaklanan farklar yerine
öncelik listesinde hangi yolların kaldığı ölçülür.

Halk sağlığıyla yakınsaklık kontrolü, ilçe bazında yol uzunluğuna göre
ağırlıklandırılmış LST ile açık veri kaynaklı 65+ yaş oranını karşılaştırır.
İlçe sayısı ve Pearson/Spearman ilişkileri
`heat_health_convergence.csv` içindedir. Yaş oranı HVI bileşeni olduğundan
bu, bağımsız bir doğruluk testi değil; ham ısı haritası ile sağlık açısından
hassas yaş grubu dağılımının örtüşme kontrolüdür. Mahalle düzeyinde yaş
verisi olmadığı için sonuç ilçe ölçeğini aşan bir iddiada bulunmaz.

Senaryolar son yılın eşit ağırlıklı HVI sıralamasındaki varsayılan ilk %20
yol segmentine uygulanır. Başlangıç varsayımları ağaç senaryosunda NDVI
`+0.15`, gölgeleme senaryosunda LST `-2°C` ve birleşik senaryoda ikisidir.
`--target-share`, `--ndvi-delta` ve `--cooling-c` ile değiştirilebilir.
Çıktı ortalama HVI değişimine ek olarak hedeflenen yolların 65+ oranını,
nüfus yoğunluğunu ve üst 65+ beşte birlik dilimdeki payını verir. Bu
what-if hesabı ölçülmüş ağaç/gölge etkisi, maliyet ya da sağlık sonucu
değildir.

Analiz ürünleri `data/processed/<şehir>/impact_analysis/` altına yazılır:
`annual_weather_adjusted.csv`, `robustness.csv`,
`heat_health_convergence.csv`, `intervention_scenarios.csv`,
`impact_scenarios.geojson`, `analysis_summary.json` ve
`analysis_map.html`. GeoJSON büyük olduğundan harita dosya URL'si ile
değil, bu klasörde bir yerel HTTP sunucusu açılarak görüntülenir:

```bash
cd data/processed/izmir/impact_analysis
python -m http.server 8000
```

Ardından `http://localhost:8000/analysis_map.html` adresini açın.

## 2020 → 2026: Bulgular

*(İzmir, 6 yıllık pencere. Her yıl için 4 uydu karosunda karo başına 3,
toplam 12 temmuz-ağustos Landsat sahnesinin piksel bazlı medyanı. Sayılar
haritanın da beslendiği aynı veri setinden: `data/processed/izmir/
roads_timeseries.geojson` ve `roads_with_hvi.geojson`. Hangi sahnelerin
kullanıldığı `docs/izmir/manifest.json` içinde.)*

**Sıcaklık - genel eğilim:**
- 44.041 yol segmentinin ortalama yüzey sıcaklığı 2020'de 42,6 °C, 2026'da
  43,1 °C: ortalama değişim **+0,47 °C**.
- En çok ısınan yol: **+13,5 °C** · en çok soğuyan yol: **-7,6 °C**
- Yolların **%49'u** ısındı (+0,5 °C'den fazla), **%23'ü** soğudu, **%27'si**
  pratik olarak değişmedi. Yalnızca %1,6'sı +3 °C ve üzeri ısındı.

> **Önceki sürümlerdeki "+3,29 °C" rakamı hakkında:** v1.x README'si ortalama
> +3,29 °C ısınma ve "yolların %98'i ısındı" diyordu. O sayılar karo başına
> **tek** sahneden üretilmişti ve iki yılın seçilen günleri arasındaki hava
> farkını yansıtıyordu. Aynı karonun üç sahnesinin medyanı alındığında fark
> +0,47 °C'ye iniyor. Ders: tek bir uydu geçişinden yıllar arası ısınma
> sonucu çıkarılmaz.

**HVI - risk dağılımı (gruplu metodoloji, 5 kategori, iki yılın ortak
Jenks sınırlarıyla; demografisi eşlenen 43.183 yol):**

| Kategori | 2020 | 2026 | Değişim |
|---|---|---|---|
| Düşük | 7.462 | 5.659 | -1.803 |
| Orta | 11.902 | 12.091 | +189 |
| Yüksek | 9.569 | 10.739 | +1.170 |
| Kritik | 9.694 | 9.799 | +105 |
| Aşırı Kritik | 4.556 | 4.895 | +339 |

Kategori sınırları iki yılın ortak dağılımından bir kez hesaplandığı için
"Kritik" her iki yılda aynı eşiği ifade eder. Kayma esas olarak alt uçta:
Düşük kategorisinden çıkan yollar Orta ve Yüksek'e geçmiş; Kritik ve Aşırı
Kritik toplamı **%3 artmış** (14.250'den 14.694'e). Demografi ve OSM
bileşenleri iki yılda aynı olduğu için bu değişimin tamamı sıcaklık ve
bitki örtüsünden gelir.

> Not: bu sayılar v1.x'tekilerle karşılaştırılamaz. v2.0.0'da endeks gruplu
> yapıya geçti, ölçekleme değişti ve sıcaklık girdisi tek sahne yerine
> medyan kompozitten geliyor.

**En yüksek ortalama HVI'ye sahip 5 mahalle (2026, en az 20 yol segmenti
olan 418 mahalle arasından):**

1. Umut Mahallesi (Karabağlar) - %90,4
2. Sarıyer Mahallesi (Karabağlar) - %89,7
3. Uğur Mumcu Mahallesi (Karabağlar) - %89,4
4. İhsan Alyanak Mahallesi (Karabağlar) - %88,5
5. Bozyaka Mahallesi (Karabağlar) - %86,4

İlçe ortalamasında Karabağlar (%70,5) açık ara önde; ardından Buca (%56,2),
Bayraklı (%55,3) ve Karşıyaka (%53,7) geliyor. Listenin başı v1.x ile büyük
ölçüde aynı mahalleler: sonuç, formül değişikliğine karşı kararlı.

**Grupların endekse gerçek etkisi (2026, grup skoru ile HVI arasındaki sıra
korelasyonu):** maruziyet 0,82 · tehlike 0,39 · kırılganlık 0,23. Üç grubun
ağırlığı eşit olsa da etkileri eşit değil: İzmir'de riskin mekânsal
dağılımını en çok nüfus ve yapılaşma yoğunluğu belirliyor. Yani bu harita
ağırlıklı olarak "sıcak VE kalabalık" yerleri öne çıkarır; kırılganlık
bileşenleri ilçe düzeyinde olduğu için mahalle içi ayrımı zayıftır.

**Ne yapılabilir?**
- Kritik/Aşırı Kritik kategorisindeki 14.694 yol segmenti (skorlu yolların
  ~%34'ü) ağaçlandırma, gölgelendirme, açık renk yüzey gibi müdahaleler için
  önceliklendirilebilir.
- Bir yolun HVI'si haritadaki tooltip'ten "neden" sorusuyla birlikte
  okunabiliyor - ör. bir yol hem sıcak hem ağaçsız hem hastaneye uzaksa,
  bu üç ayrı müdahale türünü (gölgelendirme, sağlık erişimi planlaması,
  acil durum hazırlığı) aynı anda işaret eder.
- İzlemenin sürdürülmesi öneriliyor - `--years` parametresiyle gelecek
  yıllar kolayca eklenebilir.

**Metodolojik uyarı:** +0,47 °C, iki yılın yaz medyan kompozitleri
arasındaki yüzey sıcaklığı farkıdır ve uzun dönem iklim trendi olarak
yorumlanmamalıdır. İki nokta bir trend belirlemez; medyan kompozit
tek-günlük anomalileri azaltır ama o yazın genel hava koşullarını
(sıcak/serin yaz, toprak nemi) gidermez. Hava koşullarından arındırılmış
çok yıllı bir tahmin için `analyze_pipeline.py` kullanılabilir.

## Kurulum ve çalıştırma

```bash
git clone <bu-repo>
cd turkiye-heat-risk
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

`requirements.txt`'teki sürüm aralıkları major sürüm kırılımlarına karşı
üst sınırlıdır ama yine de bir aralıktır; bugün çalışan tam ortamı birebir
yeniden üretmek için (`rasterio`/`geopandas` gibi GDAL tabanlı paketler
minor sürümde bile davranış değiştirebiliyor) `constraints.txt`'teki
sabitlenmiş sürümlerle kurun:

```bash
pip install -r requirements.txt -c constraints.txt
```

Tüm hattı (indirme → LST/NDVI → yol eşleme → HVI → harita) çalıştırmak için:

```bash
python pipeline.py --city izmir --years 2020 2026 --main-year 2026 --open
```

- `--city`: `src/cities/<sehir>/config.yaml` içindeki şehir kimliği (varsayılan: `izmir`)
- `--years`: karşılaştırılacak yıllar (2 veya daha fazla olabilir)
- `--main-year`: hangi yılın "ana/düz" klasör yapısını kullanacağı
  (`data/raw/<sehir>/...` vs. `data/raw/<sehir>/<yıl>/...`)
- `--open`: harita üretildikten sonra otomatik tarayıcıda aç
- `--force`: yol risk skoru ve HVI önbelleğini yok say, yeniden hesapla
- `--night-lst`: mahalle ölçeğinde MODIS gece ısı adası katmanını da üret
  (isteğe bağlı, ek bir uydu kaynağı indirir - bkz. Metodoloji)

Her adım, çıktısı zaten diskte varsa atlanır - script yarıda kesilse bile
`python pipeline.py --city izmir` ile kaldığı yerden devam eder. İlk
çalıştırma (4 Landsat sahnesi × 2 yıl + OSM özütü) makul bir internet
bağlantısında ~15-25 dakika ve ~5-6 GB disk alanı gerektirir.

Yol risk skoru ve HVI çıktıları formül sürümü değiştiğinde otomatik
olarak yeniden hesaplanır (bkz. `src/core/cache.py`); veri kaynağı aynı
kalıp sadece parametre denemek isteniyorsa `--force` ile elle de
zorlanabilir.

Çok yıllı analiz paketi için yukarıdaki örnekteki yılları ana pipeline'a
verin, ardından `analyze_pipeline.py --help` ile hava katsayısı, tampon ve
müdahale varsayımlarını ayarlayın. ERA5-Land ilk çalıştırmada internet
bağlantısı ister; günlük seri şehir bazında önbelleğe alınır. Analiz işleri
sıralı yürür ve ayrı ayrı büyük rasterleri eşzamanlı işleme almaz.

## Testler

Saf/mantık ağırlıklı fonksiyonlar (normalizasyon, yüzdelik dilim
etiketleme, config doğrulama, önbellek geçerliliği) için birim testler
`tests/` altında yer alır - uydu indirme veya OSM ağı gerektirmez, saniyeler
içinde çalışır:

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

`.github/workflows/tests.yml` aynı suite'i her push ve PR'da otomatik
çalıştırır - bir katkı (ör. yeni bir şehir adaptörü) testleri kırıyorsa
merge edilmeden önce görünür.

## Docker ile çalıştırma

`rasterio`/GDAL kurulumu makineden makineye (özellikle Windows'ta) sorun
çıkarabiliyor - `Dockerfile`, "bu imaj çalışıyorsa senin makinende de
çalışır" garantisi verir. Çıktılar (`data/`, `output/`, `docs/`) konteyner
dışında kalıcı olsun diye host'a mount edilir:

```bash
docker build -t turkiye-heat-risk .
docker run --rm \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/output:/app/output" \
  -v "$(pwd)/docs:/app/docs" \
  turkiye-heat-risk --city izmir --years 2020 2026 --main-year 2026
```

`.github/workflows/tests.yml` imajın gerçekten build olduğunu ve modülün
sağlam kurulduğunu her push/PR'da otomatik doğrular (ağır/ağ gerektiren
tam pipeline'ı çalıştırmadan, hafif bir duman testiyle).

## Barındırma (GitHub Pages)

`pipeline.py`, her şehir için iki harita üretir (bkz. `core/map_builder.py`):
`output/<sehir>_hvi_map.html` (tek dosya, çevrimdışı) ve `docs/<sehir>/`
(veri ayrı küçük GeoJSON dosyalarına bölünmüş, tarayıcı sadece açılan
katmanı indirir - ilk sayfa yükü birkaç yüz KB). İkincisini yayınlamak için:

1. En az bir şehir için `python pipeline.py --city <sehir>` çalıştır.
2. `python build_docs_index.py` ile şehirler arası karşılaştırma sayfasını
   (`docs/index.html`) üret.
3. `docs/` klasörünü commit'le, GitHub'da Settings → Pages → Branch: `main`,
   klasör: `/docs` seç.

Bu deponun kendi sayfası: <https://ayberkrk.github.io/turkiye-heat-risk/>

## Tekrar üretilebilirlik: harita manifest'i

Her iki harita çıktısının (`output/<sehir>_hvi_map.html` ve
`docs/<sehir>/index.html`) yanına, hangi girdi/ayarlarla üretildiklerini
kaydeden küçük bir JSON dosyası da yazılır: sırasıyla
`output/<sehir>_hvi_manifest.json` ve `docs/<sehir>/manifest.json` (bkz.
`core/map_builder.py`, `_build_manifest`). İçeriği:

- şehir kimliği/adı, üretim zamanı (UTC)
- istenen yıllar ve ana (main) yıl
- şehir config'inin ilgili alanları (bbox, CRS, bulut oranı/karo başına
  sahne sayısı sınırı, yol tamponu, OSM admin_level'ları, pbf URL'i)
- her yıl için kullanılan Landsat sahnelerinin kimliği/tarihi/karosu/bulut
  oranı (`scene_metadata.json`'dan, bkz. `core/satellite.py`)
- formül/önbellek sürüm numaraları (`HVI_FORMULA_VERSION`,
  `RISK_TIMESERIES_VERSION`, `MOSAIC_VERSION`, `SCENE_FETCH_VERSION`)
- gece ısı adası katmanının (`--night-lst`) istenip istenmediği

Ham raster'lar, tam `roads_with_hvi.geojson` gibi büyük ara çıktılar veya
kimlik bilgisi (zaten hiçbiri saklanmıyor) manifest'e YAZILMAZ - sadece
küçük, tanımlayıcı metadata. İncelemek için:

```bash
python -m json.tool docs/izmir/manifest.json
```

## Proje yapısı

```
turkiye-heat-risk/
├── pipeline.py               # Tek üst seviye giriş noktası: python pipeline.py --city izmir
├── analyze_pipeline.py       # Çok yıllı hava/duyarlılık/what-if analiz paketi
├── validate_city.py           # Yeni bir şehir config.yaml'ını hızlıca doğrular
├── build_docs_index.py        # docs/ altındaki şehirler için karşılaştırma sayfası üretir
├── src/
│   ├── core/                  # Şehirden bağımsız, genel pipeline mantığı
│   │   ├── city_config.py     #   config.yaml yükleyici + doğrulama
│   │   ├── satellite.py       #   Landsat indirme
│   │   ├── raster.py          #   LST/NDVI hesaplama + bellek-güvenli mozaikleme
│   │   ├── roads.py           #   OSM yol ağı + yıllık sıcaklık/NDVI eşleme
│   │   ├── impact_analysis.py #   hava düzeltmesi, HVI duyarlılığı ve müdahale senaryoları
│   │   ├── osm_amenities.py   #   sağlık/yeşil alan/bina katmanları (OSM'den)
│   │   ├── hvi.py             #   çok bileşenli HVI hesaplama
│   │   ├── map_builder.py     #   interaktif Folium haritası (çevrimdışı + barındırma sürümü)
│   │   ├── night_lst.py       #   isteğe bağlı: mahalle ölçeğinde MODIS gece ısı adası katmanı
│   │   ├── cache.py           #   ara çıktılar için sürüm damgalı önbellek geçerliliği
│   │   ├── ilce_table_adapter.py #  TÜİK-şablonlu şehirlerin ortak mahalle-katmanı mantığı (2 CSV -> mahalle)
│   │   └── text_utils.py      #   şehirler arası paylaşılan Türkçe metin normalizasyonu
│   └── cities/
│       ├── izmir/
│       │   ├── config.yaml         #   İzmir'e özel bbox, URL'ler, sütun eşlemeleri
│       │   ├── adapter.py          #   İzmir'e özel nüfus/demografi mantığı (CKAN)
│       │   └── sege_2022_ilce.csv  #   İlçe bazlı sosyoekonomik gelişmişlik skoru (resmi SEGE-2022)
│       ├── eskisehir/
│       │   ├── config.yaml         #   Eskişehir'e özel bbox, URL'ler
│       │   ├── adapter.py          #   TÜİK tabanlı nüfus/demografi mantığı (CKAN'sız şablon)
│       │   ├── ilce_nufus.csv      #   İlçe nüfusu + yaşlı/çocuk oranı (TÜİK ADNKS 2025)
│       │   └── sege_2022_ilce.csv  #   İlçe bazlı sosyoekonomik gelişmişlik skoru (resmi SEGE-2022)
│       └── sanliurfa/, antalya/, mersin/, adana/  # Eskişehir ile aynı TÜİK tabanlı şablon
│           ├── config.yaml         #   şehre özel bbox/CRS/OSM bölge özütü
│           ├── adapter.py          #   ince sarmalayıcı (core/ilce_table_adapter.py'yi çağırır)
│           ├── ilce_nufus.csv      #   ilçe nüfusu + il düzeyi yaşlı/çocuk (0-14) oranı
│           └── sege_2022_ilce.csv  #   ilçe SEGE-2022 skorları (resmi PDF'ten)
├── tests/                     # Saf/mantık fonksiyonları için birim testler (ağ gerektirmez)
├── docs/                      # GitHub Pages'in servis ettiği, küçük/fetch tabanlı harita sürümü
│   ├── index.html             #   şehirler arası karşılaştırma sayfası (build_docs_index.py üretir)
│   └── <sehir>/                #   index.html + GeoJSON veri dosyaları + manifest.json (bkz. Tekrar üretilebilirlik)
├── output/                    # pipeline.py tarafından üretilir, git'e dahil değil
│   ├── <sehir>_hvi_map.html  #   tamamen çevrimdışı, tek dosyalık harita (çift tıklayıp açılabilir)
│   └── <sehir>_hvi_manifest.json  #   o haritayı üreten girdi/ayarların kaydı
├── data/                      # pipeline.py tarafından üretilir, git'e dahil değil
│   ├── raw/<sehir>/           #   indirilen Landsat bantları, OSM özütü, nüfus CSV'leri (şehir bazlı ayrılır)
│   └── processed/<sehir>/     #   LST/NDVI mozaikleri, ara GeoJSON'lar (şehir bazlı ayrılır)
├── CONTRIBUTING.md            # Yeni şehir ekleme adımları
├── requirements.txt
├── requirements-dev.txt       # Test bağımlılıkları (pytest)
├── Dockerfile / .dockerignore # Tek komutla tekrar üretilebilir çalışma ortamı
├── LICENSE                    # MIT
└── README.md
```

## Bilinen sınırlamalar

- **Bulut kapanması**: bir karo için `max_scenes_per_tile` kadar aday
  sahne birden fazla tarihten denenir (bkz. Metodoloji) ama bazı yıllarda
  İzmir üzerinde %30 altı bulutlu HİÇBİR yaz sahnesi bulunamayabilir; bu
  durumda `max_cloud_cover` gevşetilebilir ama sonuç kalitesi düşer.
- **Yaş verisinin çözünürlüğü**: yaşlı nüfus oranı ilçe seviyesinde -
  mahalle-içi gerçek dağılım bundan daha değişken olabilir.
- **Tek gündüz anlık görüntüsü**: yol bazlı LST, sahnenin çekildiği saatteki
  (Landsat için genelde öğleden sonraya yakın) sıcaklığı yansıtır. Gece ısı
  adası etkisi (genelde daha güçlü olduğu bilinir) `--night-lst` bayrağıyla
  ayrı bir katman olarak eklenebilir (MODIS, 1 km çözünürlük) ama bu katman
  yol değil mahalle ölçeğindedir ve HVI skoruna dahil değildir - bkz.
  `core/night_lst.py` ve aşağıdaki Metodoloji bölümü.
- **Doğrulanmamış endeks**: HVI, sıcak hava dalgalarındaki acil başvuru,
  ambulans çağrısı ya da ölüm verisiyle karşılaştırılmamıştır. Grup payları
  ve bileşen seçimi literatürdeki çerçeveye dayanan bir yargıdır. Harita
  "nereye önce bakılmalı" sorusuna yanıt verir; bir yolun ötekinden kaç kat
  daha tehlikeli olduğunu ölçmez.
- **Yüzey sıcaklığı hava sıcaklığı değildir**: LST, uydunun gördüğü
  yüzeyin (çatı, asfalt, ağaç tepesi) sıcaklığıdır; yayanın hissettiği hava
  sıcaklığı, nem, rüzgar ve gölge bundan farklıdır. Ağaç tepesi serin
  görünen bir sokak yaya düzeyinde gölgeli olabilir, çatıları sıcak görünen
  dar bir sokak yaya düzeyinde gölgede kalabilir.
- **Termal çözünürlük 100 m**: sıcaklık yol başına raporlansa da komşu
  sokaklar çoğunlukla aynı termal ölçümü paylaşır (bkz. Metodoloji).
- **Şehirler arası karşılaştırma**: bileşenler her şehrin kendi dağılımına
  göre ölçeklenir. Bir şehirde "Aşırı Kritik" çıkan yol, o şehrin en riskli
  yollarındandır; başka bir şehrin "Aşırı Kritik" yoluyla aynı mutlak riski
  taşıdığı anlamına gelmez.
- **10 metrelik yol tamponu**: sıcaklık ve NDVI örneklemesinde kullanılan
  bu dar tampon, çok dar sokaklarda komşu bir yolun etkisini
  karıştırabilir; çok geniş bulvarlarda ise koridorun tamamını
  kapsamayabilir. Duyarlılık paketi 30 ve 50 m alternatiflerini de ölçer;
  hangi tamponun saha gerçeğine uyduğunu kendi başına belirlemez.
- **Hava düzeltmesinin ölçeği**: ERA5-Land'in yaklaşık 11 km hava
  sıcaklığı, 30 m Landsat yüzey sıcaklığını ölçmez. Düzeltme katsayısı
  (`β`) varsayımdır ve ayrı ayrı karşılaştırılmalıdır; analiz yerel hava
  istasyonlarının yerine geçmez.
- **Senaryo varsayımları**: NDVI artışı ve LST düşüşü kullanıcı girdisidir.
  Ağaç türü, taç gelişme süresi, gölge geometrisi, su ihtiyacı, uygulama
  maliyeti veya maruziyet davranışı modellenmez. Haritadaki fark varsayımlı
  HVI aritmetiğidir, gerçekleşmesi beklenen sağlık etkisi değildir.
- **150 metrelik yapılaşma tamponu**: bina yoğunluğu için seçilen bu
  yarıçap makul bir kentsel doku ölçeğidir ama tek bir seçimdir; komşu
  yolların tamponları örtüştüğü için yakın yollar benzer yoğunluk değeri
  alır, yani bu bileşen yol ölçeğinden çok mahalle ölçeğinde ayrıştırır.
- **SEGE tablosu elle aktarılmıştır**: `sege_2022_ilce.csv` içindeki
  skorlar resmi rapordan elle çıkarılmıştır; 30 ilçenin tamamı T.C. Sanayi
  ve Teknoloji Bakanlığı'nın resmi SEGE-2022 raporuyla satır satır
  karşılaştırılmış ve doğrulanmıştır. Yine de rapor güncellendiğinde bu
  dosyanın elle yeniden kontrol edilmesi gerekir.
- **Sosyoekonomik bileşen ilçe seviyesinde**: SEGE-2022 skoru da (yaşlı/
  çocuk oranı gibi) ilçe seviyesinde - mahalle-içi gerçek dağılım bundan
  daha değişken olabilir. Ayrıca 2022 tarihli, tek seferlik bir araştırma;
  gelecekte güncellenmiş bir SEGE raporu yayımlanırsa
  `sege_2022_ilce.csv` güncellenmelidir.
- **Tek ilçeli şehirler**: 70 şehrin 54'ü tek ilçe kapsar; bu şehirlerde
  nüfus yoğunluğu, yaşlı/çocuk oranı ve SEGE bileşenleri tüm mahallelerde
  aynı değeri alır, HVI'ı ayırt etmez ve endekse alınmaz. Harita yalnızca
  LST, NDVI, yapılaşma ve erişim bileşenlerini yansıtır. Ayrıca Ağrı, Iğdır, Kırklareli ve
  Karaman'da ilçe sayımı il düzeyinden inandırıcı olmayacak kadar
  saptığı için il düzeyi 0-14/65+ oranları kullanılır.
- **TÜİK-şablonlu ana şehirlerde (Eskişehir, Şanlıurfa, Antalya, Mersin, Adana)
  bir kademe daha kaba çözünürlük**: İzmir'in mahalle seviyesinde CKAN
  nüfus verisinin aksine bu adapter'lar yaşlı/çocuk oranı için ilçe bazlı
  bir TÜİK yayını bulamadığından İL'in genel yaş dağılımını (0-14 ve 65+)
  tüm ilçelere aynı şekilde uyguluyor; nüfus yoğunluğu da mahalle değil
  ilçe bazında sabit (ilçe alanı OSM idari sınırından hesaplandığı için
  kırsal hinterlandı geniş ilçelerde yoğunluk düşük çıkar). Gerçek
  ilçe-içi/mahalle-içi eşitsizlik bu yüzden İzmir'e göre daha az görünür
  (bkz. `core/ilce_table_adapter.py` ve her şehrin `adapter.py`
  docstring'i).

## Lisans

MIT. Bkz. [LICENSE](LICENSE).
