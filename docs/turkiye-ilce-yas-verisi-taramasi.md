# Türkiye'de ilçe düzeyinde yaş verisi taraması

**Güncelleme:** 25 Eylül 2026  
**Kapsam:** 81 ilin tamamı tarandı; ilçe yaş verisi kaynağı kayıtlı olan ve gerçek OSM verisiyle HVI kapsamı yeterli çıkan 63 şehir `src/cities/` altında tutulur (İzmir dahil). 18 aday, kapsam eşiğini geçemediği için elendi.

Bu sayfa şehirlerin veri kaynağını, kapsadığı ilçeleri ve OSM ile ölçülen HVI kapsamını kaydeder. Kapsam, bbox içindeki yolların kaçının demografisi eşlenmiş bir mahalleye düştüğünü gösterir (`python validate_city.py <sehir> --osm-coverage`).

## Eklenen şehirler

| Şehir | İlçe kapsamı | Veri yılı | Kaynak | HVI kapsamı | Not |
| --- | --- | ---: | --- | ---: | --- |
| İzmir | Tüm ilçeler | 2022 | Belediye açık veri (CKAN), mahalle düzeyi | n/a | Mahalle bazlı canlı veri |
| Adana | Seyhan, Yüreğir, Çukurova, Sarıçam | 2025 | İlçe nüfusu ADNKS 2025 (il toplamına eşit); 0-14/65+ oranları il düzeyi, [nufusune.com il sayfası (TÜİK ADNKS 2025)](https://nufusune.com/) | %95 | Çekirdek ilçeler; oranlar il düzeyinden |
| Adıyaman | Merkez | 2022 | [İŞKUR raporu](https://media.iskur.gov.tr/94746/adiyaman.pdf) | %87 | İlçe sayımları kaynak raporundan |
| Ağrı | Merkez | 2025 | Oranlar il düzeyi, [nufusune.com il sayfası (TÜİK ADNKS 2025)](https://nufusune.com/); nüfus [İŞKUR raporu](https://media.iskur.gov.tr/57059/agri.pdf) | %97 | İlçe sayımı il düzeyinden çok saptığı için il oranı kullanıldı |
| Amasya | Amasya Merkez | 2021 | [İŞKUR raporu](https://media.iskur.gov.tr/57061/amasya.pdf) | %90 | İlçe sayımları kaynak raporundan |
| Ankara | Çankaya, Keçiören, Yenimahalle | 2021 | [İŞKUR raporu](https://media.iskur.gov.tr/71959/ankara.pdf) | %83 | İlçe sayımları kaynak raporundan |
| Antalya | Muratpaşa, Konyaaltı, Kepez, Döşemealtı, Aksu | 2025 | İlçe nüfusu ADNKS 2025 (il toplamına eşit); 0-14/65+ oranları il düzeyi, [nufusune.com il sayfası (TÜİK ADNKS 2025)](https://nufusune.com/) | %86 | Çekirdek ilçeler; oranlar il düzeyinden |
| Balıkesir | Altıeylül, Karesi | 2022 | [İŞKUR raporu](https://media.iskur.gov.tr/94373/balikesir.pdf) | %72 | İlçe sayımları kaynak raporundan |
| Batman | Merkez | 2022 | [İŞKUR raporu](https://media.iskur.gov.tr/94375/batman.pdf) | %97 | İlçe sayımları kaynak raporundan |
| Bayburt | Merkez | 2025 | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) | %97 | İlçe sayımları kaynak raporundan |
| Bilecik | Merkez | 2025 | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) | %87 | İlçe sayımları kaynak raporundan |
| Bingöl | Merkez | 2021 | [İŞKUR raporu](https://media.iskur.gov.tr/71969/bingol.pdf) | %90 | İlçe sayımları kaynak raporundan |
| Bitlis | Merkez | 2022 | [İŞKUR raporu](https://media.iskur.gov.tr/71970/bitlis.pdf) | %95 | İlçe sayımları kaynak raporundan |
| Bolu | Merkez | 2025 | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) | %91 | İlçe sayımları kaynak raporundan |
| Burdur | Merkez | 2022 | [İŞKUR raporu](https://media.iskur.gov.tr/94764/burdur.pdf) | %99 | İlçe sayımları kaynak raporundan |
| Bursa | Nilüfer, Osmangazi, Yıldırım | 2023 | [İŞKUR raporu](https://media.iskur.gov.tr/94382/bursa.pdf) | %97 | İlçe sayımları kaynak raporundan |
| Çanakkale | Merkez | 2025 | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) | %89 | İlçe sayımları kaynak raporundan |
| Çorum | Merkez | 2025 | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) | %92 | İlçe sayımları kaynak raporundan |
| Denizli | Merkezefendi | 2025 | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) | %84 | İlçe sayımları kaynak raporundan |
| Diyarbakır | Bağlar, Kayapınar, Sur, Yenişehir | 2023 | [İŞKUR raporu](https://media.iskur.gov.tr/94770/diyarbakir.pdf) | %93 | İlçe sayımları kaynak raporundan |
| Edirne | Merkez | 2025 | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) | %100 | İlçe sayımları kaynak raporundan |
| Elazığ | Merkez | 2023 | [İŞKUR raporu](https://media.iskur.gov.tr/94773/elazig.pdf) | %70 | İlçe sayımları kaynak raporundan |
| Erzincan | Merkez | 2022 | [İŞKUR raporu](https://media.iskur.gov.tr/94774/erzincan.pdf) | %90 | İlçe sayımları kaynak raporundan |
| Erzurum | Aziziye, Palandöken, Yakutiye | 2022 | [İŞKUR raporu](https://media.iskur.gov.tr/94392/erzurum.pdf) | %100 | İlçe sayımları kaynak raporundan |
| Eskişehir | Odunpazarı, Tepebaşı | 2025 | İlçe nüfusu ADNKS 2025 (il toplamına eşit); 0-14/65+ oranları il düzeyi, [nufusune.com il sayfası (TÜİK ADNKS 2025)](https://nufusune.com/) | %75 | Çekirdek ilçeler; oranlar il düzeyinden |
| Gaziantep | Şahinbey, Şehitkamil | 2023 | [İŞKUR raporu](https://media.iskur.gov.tr/94394/gaziantep.pdf) | %100 | İlçe sayımları kaynak raporundan |
| Gümüşhane | Merkez | 2022 | [İŞKUR raporu](https://media.iskur.gov.tr/94779/gumushane.pdf) | %87 | İlçe sayımları kaynak raporundan |
| Hatay | Antakya | 2022 | [İŞKUR raporu](https://media.iskur.gov.tr/94781/hatay.pdf) | %62 | İlçe sayımları kaynak raporundan |
| Iğdır | Merkez | 2025 | Oranlar il düzeyi, [nufusune.com il sayfası (TÜİK ADNKS 2025)](https://nufusune.com/); nüfus [İŞKUR raporu](https://media.iskur.gov.tr/71988/igdir.pdf) | %60 | İlçe sayımı il düzeyinden çok saptığı için il oranı kullanıldı |
| Isparta | Merkez | 2022 | [İŞKUR raporu](https://media.iskur.gov.tr/71989/isparta.pdf) | %94 | İlçe sayımları kaynak raporundan |
| İstanbul | Fatih | 2025 | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) | %65 | İlçe sayımları kaynak raporundan |
| Kahramanmaraş | Onikişubat | 2025 | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) | %94 | İlçe sayımları kaynak raporundan |
| Karabük | Merkez, Safranbolu | 2022 | [İŞKUR raporu](https://media.iskur.gov.tr/94787/karabuk.pdf) | %65 | İlçe sayımları kaynak raporundan |
| Karaman | Merkez | 2025 | Oranlar il düzeyi, [nufusune.com il sayfası (TÜİK ADNKS 2025)](https://nufusune.com/); nüfus [İŞKUR raporu](https://media.iskur.gov.tr/71994/karaman.pdf) | %69 | İlçe sayımı il düzeyinden çok saptığı için il oranı kullanıldı |
| Kars | Merkez | 2022 | [İŞKUR raporu](https://media.iskur.gov.tr/94789/kars.pdf) | %91 | İlçe sayımları kaynak raporundan |
| Kastamonu | Merkez | 2022 | [İŞKUR raporu](https://media.iskur.gov.tr/94790/kastamonu.pdf) | %92 | İlçe sayımları kaynak raporundan |
| Kayseri | Kocasinan, Melikgazi, Talas | 2022 | [İŞKUR raporu](https://media.iskur.gov.tr/94791/kayseri.pdf) | %99 | İlçe sayımları kaynak raporundan |
| Kilis | Merkez | 2025 | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) | %96 | İlçe sayımları kaynak raporundan |
| Kırıkkale | Merkez | 2022 | [İŞKUR raporu](https://media.iskur.gov.tr/94793/kirikkale.pdf) | %95 | İlçe sayımları kaynak raporundan |
| Kırklareli | Merkez | 2025 | Oranlar il düzeyi, [nufusune.com il sayfası (TÜİK ADNKS 2025)](https://nufusune.com/); nüfus [İŞKUR raporu](https://media.iskur.gov.tr/94794/kirklareli.pdf) | %100 | İlçe sayımı il düzeyinden çok saptığı için il oranı kullanıldı |
| Kocaeli | Başiskele, Derince, Gölcük, İzmit, Kartepe, Körfez | 2023 | [İŞKUR raporu](https://media.iskur.gov.tr/94796/kocaeli.pdf) | %99 | İlçe sayımları kaynak raporundan |
| Konya | Karatay, Meram, Selçuklu | 2023 | [İŞKUR raporu](https://media.iskur.gov.tr/94797/konya.pdf) | %100 | İlçe sayımları kaynak raporundan |
| Kütahya | Merkez | 2022 | [İŞKUR raporu](https://media.iskur.gov.tr/94798/kutahya.pdf) | %71 | İlçe sayımları kaynak raporundan |
| Malatya | Yeşilyurt | 2025 | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) | %81 | İlçe sayımları kaynak raporundan |
| Manisa | Yunusemre | 2025 | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) | %73 | İlçe sayımları kaynak raporundan |
| Mersin | Yenişehir, Akdeniz, Mezitli, Toroslar | 2025 | İlçe nüfusu ADNKS 2025 (il toplamına eşit); 0-14/65+ oranları il düzeyi, [nufusune.com il sayfası (TÜİK ADNKS 2025)](https://nufusune.com/) | %68 | Çekirdek ilçeler; oranlar il düzeyinden |
| Muğla | Menteşe | 2022 | [İŞKUR raporu](https://media.iskur.gov.tr/94803/mugla.pdf) | %91 | İlçe sayımları kaynak raporundan |
| Muş | Merkez | 2025 | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) | %76 | İlçe sayımları kaynak raporundan |
| Niğde | Merkez | 2022 | [İŞKUR raporu](https://media.iskur.gov.tr/94342/nigde.pdf) | %99 | İlçe sayımları kaynak raporundan |
| Ordu | Altınordu | 2025 | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) | %93 | İlçe sayımları kaynak raporundan |
| Rize | Merkez | 2025 | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) | %91 | İlçe sayımları kaynak raporundan |
| Sakarya | Adapazarı | 2025 | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) | %60 | İlçe sayımları kaynak raporundan |
| Samsun | İlkadım | 2025 | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) | %82 | İlçe sayımları kaynak raporundan |
| Şanlıurfa | Eyyübiye, Haliliye, Karaköprü | 2025 | İlçe nüfusu ADNKS 2025 (il toplamına eşit); 0-14/65+ oranları il düzeyi, [nufusune.com il sayfası (TÜİK ADNKS 2025)](https://nufusune.com/) | %92 | Çekirdek ilçeler; oranlar il düzeyinden |
| Sinop | Merkez | 2025 | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) | %100 | İlçe sayımları kaynak raporundan |
| Sivas | Merkez | 2022 | [İŞKUR raporu](https://media.iskur.gov.tr/94350/sivas.pdf) | %100 | İlçe sayımları kaynak raporundan |
| Tekirdağ | Süleymanpaşa | 2025 | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) | %100 | İlçe sayımları kaynak raporundan |
| Trabzon | Ortahisar | 2025 | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) | %98 | İlçe sayımları kaynak raporundan |
| Tunceli | Merkez | 2025 | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) | %68 | İlçe sayımları kaynak raporundan |
| Uşak | Merkez | 2025 | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) | %98 | İlçe sayımları kaynak raporundan |
| Van | İpekyolu | 2025 | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) | %70 | İlçe sayımları kaynak raporundan |
| Yalova | Merkez | 2025 | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) | %100 | İlçe sayımları kaynak raporundan |
| Zonguldak | Merkez | 2025 | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) | %80 | İlçe sayımları kaynak raporundan |

SEGE-2022 ilçe sıralama/skorları, ilgili şehir CSV'lerinde aynı adlandırmayla Bakanlığın [SEGE-2022 ilçe raporuna](https://www.kalkinmakutuphanesi.gov.tr/assets/upload/dosyalar/2022-ilce-sege.pdf) göre kaydedilir. `KADEME` sütunu SEGE skor eşiklerinden bir testle doğrulanır.

81 ilin tamamı için 2007-2025 ilçe yaş grubu serisi sunan [DrDataStats sorgusu](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) verinin kaynağını TÜİK olarak belirtir. Sorgu aday taraması ve karşılaştırma için kullanılır; şehir eklemesinde seçilen ilçenin 0-14, 15-64 ve 65+ değerleri aynı yılın ilçe toplamıyla karşılaştırılır. Manisa/Yunusemre için 2025 değerleri sırasıyla 56.329, 190.289, 23.737 ve toplam 270.355'tir; Bilecik Merkez için 14.430, 59.960, 8.473 ve 82.863; Bolu Merkez için 38.018, 159.060, 25.511 ve 222.589; Çanakkale Merkez için 31.420, 149.887, 27.306 ve 208.613; Çorum Merkez için 55.428, 205.544, 38.593 ve 299.565; Denizli/Merkezefendi için 71.295, 244.813, 34.977 ve 351.085; Düzce Merkez için 54.185, 185.325, 27.739 ve 267.249; Edirne Merkez için 28.439, 145.612, 26.702 ve 200.753; Kahramanmaraş/Onikişubat için 112.588, 300.352, 34.651 ve 447.591; Kilis Merkez için 35.574, 89.683, 10.173 ve 135.430; Kırşehir Merkez için 30.406, 114.076, 18.886 ve 163.368; Malatya/Yeşilyurt için 68.611, 211.455, 29.824 ve 309.890; Mardin/Artuklu için 60.479, 127.984, 10.255 ve 198.718; Yozgat Merkez için 18.815, 77.576, 12.651 ve 109.042; Zonguldak Merkez için 16.416, 80.421, 18.442 ve 115.279; Bayburt Merkez için 12.539, 47.933, 8.243 ve 68.715; Rize Merkez için 28.937, 106.807, 17.853 ve 153.597; Hakkâri Merkez için 18.171, 53.847, 4.147 ve 76.165; Van/İpekyolu için 101.875, 242.561, 18.380 ve 362.816; Samsun/İlkadım için 60.733, 227.978, 41.579 ve 330.290; Osmaniye Merkez için 72.522, 187.535, 24.838 ve 284.895; Sinop Merkez için 10.437, 48.505, 11.369 ve 70.311; Uşak Merkez için 46.553, 186.925, 31.893 ve 265.371; Yalova Merkez için 29.027, 108.547, 20.327 ve 157.901; Ordu/Altınordu için 44.857, 165.724, 29.133 ve 239.714; Tunceli/Merkez için 6.681, 29.851, 4.513 ve 41.045; Muş/Merkez için 63.031, 130.236, 10.543 ve 203.810; Sakarya/Adapazarı için 55.589, 195.315, 33.102 ve 284.006; Şırnak/Merkez için 32.061, 70.016, 3.620 ve 105.697; Tekirdağ/Süleymanpaşa için 35.655, 160.581, 30.346 ve 226.582; Trabzon/Ortahisar için 63.269, 231.654, 40.193 ve 335.116; İstanbul/Fatih için 54.781, 251.243, 45.762 ve 351.786'dır. Her ilçede üç yaş grubunun toplamı nüfusla eşleşir. İlçe SEGE kayıtları Bakanlığın [raporunda](https://www.kalkinmakutuphanesi.gov.tr/assets/upload/dosyalar/2022-ilce-sege.pdf) kontrol edilmiş; tarama bulguları [araştırma notlarında](https://www.sanayi.gov.tr/assets/pdf/birimler/2022-ilce-sege.pdf) karşılaştırılmıştır.

## OSM kapsam denetimi

CSV bütünlük testleri tek başına yetmez: bbox yanlış yerdeyse ya da CSV'deki merkez ilçe adı OSM'dekiyle ("Merkez" ile "<İl> Merkez") eşleşmiyorsa tüm yolların demografisi NaN kalır ve HVI hesabı Jenks aşamasında çöker. Bu yüzden her şehir gerçek bölge özütüyle ölçüldü: `tools/fit_city_bbox.py` bbox'ı yoğun mahalle kümesinden çizer ve kapsamı `core/coverage.py` ile hesaplar. Eşik %60'tır; altındaki şehirler elendi. Ölçüm 25 Eylül 2026 tarihli openstreetmap.fr Türkiye bölge özütleriyle yapıldı, OSM güncellendikçe sayılar oynayabilir.

Ana şehirlerin (Antalya, Mersin, Adana, Şanlıurfa, Eskişehir) mevcut bbox'larıyla ölçülen kapsamı tablodadır; `fit_city_bbox.py` bu şehirler için daha yüksek kapsam veren bir bbox önerebilir (Mersin %86, Eskişehir %92), ama mevcut çıktılar değişmesin diye bbox'lara dokunulmadı.

## Kaynak tutarlılık taraması

Şehirlerin ilçe oranları il düzeyi oranlarla karşılaştırıldı. Merkez ilçenin yaşlı oranı il ortalamasından birkaç puan sapabilir, bu doğaldır. Ancak beş şehirde çocuk oranı il ortalamasından inandırıcı olmayacak kadar saptı (Kırklareli, Ağrı, Iğdır, Siirt, Karaman). Bu satırlar il düzeyi 0-14/65+ oranlarıyla değiştirildi (üç yaş grubunun toplamı il toplamına eşit çıkarak doğrulandı): Kırklareli, Ağrı, Iğdır ve Karaman için bu oranlar kullanılıyor; Siirt zaten elendi.

## Elenen şehirler

Aşağıdaki şehirler gerçek OSM verisiyle ölçülen HVI kapsamı %60'ın altında kaldığı için repodan çıkarıldı. Sebep genellikle OSM mahalle poligonlarının kentsel dokuyu tam kaplamaması ya da bbox içinde demografisi eşlenmiş mahalle sayısının çok az olmasıdır; veri doğru olsa bile bu şehirlerde harita güvenilir olmaz. Kapsamı düzelten OSM verisi ya da ilçe ayrımı geldiğinde `tools/fit_city_bbox.py` ile yeniden denenebilir.

| Şehir | Sonuç |
| --- | --- |
| Afyonkarahisar | HVI kapsamı %54 |
| Aksaray | HVI kapsamı %51 |
| Ardahan | HVI kapsamı %21 |
| Artvin | HVI kapsamı %39 |
| Aydın | HVI kapsamı %59 |
| Bartın | HVI kapsamı %23 |
| Çankırı | HVI kapsamı %42 |
| Düzce | HVI kapsamı %35 |
| Giresun | HVI kapsamı %41 |
| Hakkâri | HVI kapsamı %54 |
| Kırşehir | HVI kapsamı %21 |
| Mardin | HVI kapsamı %52 |
| Nevşehir | HVI kapsamı %40 |
| Osmaniye | HVI kapsamı %20 |
| Siirt | HVI kapsamı %43 |
| Şırnak | HVI kapsamı %18 |
| Tokat | HVI kapsamı %52 |
| Yozgat | HVI kapsamı %28 |

## Tek ilçeli şehir sınırlaması

47 şehir tek ilçe kapsıyor. Tek ilçede nüfus yoğunluğu, yaşlı oranı, çocuk oranı ve SEGE bileşenleri tüm mahallelerde aynı değeri alır; bu bileşenler HVI'ı ayırt etmez ve sonuç fiilen yalnızca LST, NDVI ve altyapı bileşenlerine dayanır. Bu şehirlerin haritaları ısı ve yeşil örtü desenini gösterir, demografik hassasiyeti göstermez.

## Doğrulama ölçütü

1. Yaş grubu sayımları kurumsal rapor veya TÜİK tablosunda bulunmalı.
2. 0-14 + 15-64 + 65+ toplamı, aynı kaynaktaki genel nüfus toplamına eşit olmalı.
3. `YASLI_ORAN` ve `COCUK_ORAN` sayımlardan hesaplanmalı. İlçe sayımı inandırıcı değilse (il ortalamasından çok sapıyorsa) il düzeyi oranlar belgelenerek kullanılabilir.
4. SEGE-2022 satırı ve OSM'deki idari ad eşlemesi kontrol edilmeli; `KADEME` skor eşiğiyle tutmalı.
5. Rapor yılı ile ADNKS veri yılı farklıysa veri yılı esas alınmalı.
6. Gerçek OSM ile HVI kapsamı en az %60 olmalı (`validate_city.py --osm-coverage`).
