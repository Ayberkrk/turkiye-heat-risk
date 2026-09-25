# Türkiye'de ilçe düzeyinde yaş verisi taraması

**Güncelleme:** 25 Eylül 2026  
**Kapsam:** Şehir adaptörüne eklenebilmesi için ilçe (veya merkez ilçe) düzeyinde 0–14, 15–64 ve 65+ nüfus sayımlarının birincil/kurumsal kaynakta bulunması; oranların toplam nüfusla uyuşması; ayrıca SEGE-2022 ilçe eşlemesinin yapılabilmesi.

Bu sayfa, 81 ilin tam veri tabanı değildir. “Henüz doğrulanmadı” kaydı, kaynakta veri olmadığını değil, bu tarama sırasında şehir eklemeye yetecek düzeyde doğrulama yapılmadığını belirtir. Yalnızca tamamı doğrulanmış şehirler `src/cities/` altında tutulur. Merkez ilçeye ilişkin veri bulunan illerde kapsam, kaynağın desteklediği çekirdek ilçe(ler) ile sınırlı olabilir.

## Doğrulanmış ve eklenmiş iller

| İl | İlçe yaş verisi yılı | Durum | Kaynak |
| --- | ---: | --- | --- |
| Adana | 2022 | Mevcut şehir verisi | [İŞKUR raporu](https://media.iskur.gov.tr/94370/adana.pdf) |
| Afyonkarahisar | 2022 | Eklendi | [İŞKUR raporu](https://media.iskur.gov.tr/72033/afyonkarahisar.pdf) |
| Amasya | 2021 | Eklendi | [İŞKUR raporu](https://media.iskur.gov.tr/57061/amasya.pdf) |
| Aksaray | 2022 | Eklendi | [İŞKUR raporu](https://media.iskur.gov.tr/94366/aksaray.pdf) |
| Ardahan | 2021 | Eklendi; Merkez ilçesi | [İŞKUR raporu](https://media.iskur.gov.tr/71960/ardahan.pdf) |
| Çankırı | 2022 | Eklendi; Merkez ilçesi | [İŞKUR raporu](https://media.iskur.gov.tr/71975/cankiri.pdf) |
| Ankara | 2021 | Mevcut şehir verisi | [İŞKUR raporu](https://media.iskur.gov.tr/71959/ankara.pdf) |
| Antalya | 2022 | Mevcut şehir verisi | [İŞKUR raporu](https://media.iskur.gov.tr/94375/antalya.pdf) |
| Adıyaman | 2022 | Eklendi | [İŞKUR raporu](https://media.iskur.gov.tr/94746/adiyaman.pdf) |
| Ağrı | 2021 | Eklendi | [İŞKUR raporu](https://media.iskur.gov.tr/57059/agri.pdf) |
| Artvin | 2021 | Eklendi | [İŞKUR raporu](https://media.iskur.gov.tr/71961/artvin.pdf) |
| Aydın | 2022 | Mevcut şehir verisi | [İŞKUR raporu](https://media.iskur.gov.tr/71962/aydin.pdf) |
| Balıkesir | 2022 | Mevcut şehir verisi | [İŞKUR raporu](https://media.iskur.gov.tr/94373/balikesir.pdf) |
| Bitlis | 2022 | Eklendi | [İŞKUR raporu](https://media.iskur.gov.tr/71970/bitlis.pdf) |
| Bursa | 2023 | Mevcut şehir verisi | [İŞKUR raporu](https://media.iskur.gov.tr/94382/bursa.pdf) |
| Diyarbakır | 2023 | Mevcut şehir verisi | [İŞKUR raporu](https://media.iskur.gov.tr/94770/diyarbakir.pdf) |
| Elazığ | 2023 | Mevcut şehir verisi | [İŞKUR raporu](https://media.iskur.gov.tr/94773/elazig.pdf) |
| Erzurum | 2022 | Mevcut şehir verisi | [İŞKUR raporu](https://media.iskur.gov.tr/94392/erzurum.pdf) |
| Eskişehir | 2022 | Mevcut şehir verisi | [İŞKUR raporu](https://media.iskur.gov.tr/94388/eskisehir.pdf) |
| Gaziantep | 2023 | Mevcut şehir verisi | [İŞKUR raporu](https://media.iskur.gov.tr/94394/gaziantep.pdf) |
| Gümüşhane | 2022 | Eklendi | [İŞKUR raporu](https://media.iskur.gov.tr/94779/gumushane.pdf) |
| Giresun | 2022 | Eklendi; Merkez ilçesi | [İŞKUR raporu](https://media.iskur.gov.tr/94778/giresun.pdf) |
| Hatay | 2022 | Eklendi; Antakya ilçesi | [İŞKUR raporu](https://media.iskur.gov.tr/94781/hatay.pdf) |
| Iğdır | 2022 | Eklendi; Merkez ilçesi | [İŞKUR raporu](https://media.iskur.gov.tr/71988/igdir.pdf) |
| Erzincan | 2022 | Eklendi; Merkez ilçesi | [İŞKUR raporu](https://media.iskur.gov.tr/94774/erzincan.pdf) |
| Isparta | 2022 | Eklendi; Merkez ilçesi | [İŞKUR raporu](https://media.iskur.gov.tr/71989/isparta.pdf) |
| Karaman | 2022 | Eklendi; Merkez ilçesi | [İŞKUR raporu](https://media.iskur.gov.tr/71994/karaman.pdf) |
| Kars | 2022 | Eklendi; Merkez ilçesi | [İŞKUR raporu](https://media.iskur.gov.tr/94789/kars.pdf) |
| Kırıkkale | 2022 | Eklendi; Merkez ilçesi | [İŞKUR raporu](https://media.iskur.gov.tr/94793/kirikkale.pdf) |
| İzmir | 2022 | Mevcut şehir verisi | Belediye açık veri / şehir kaynağı |
| Karabük | 2022 | Eklendi | [İŞKUR raporu](https://media.iskur.gov.tr/94787/karabuk.pdf) |
| Kayseri | 2022 | Mevcut şehir verisi | [İŞKUR raporu](https://media.iskur.gov.tr/94791/kayseri.pdf) |
| Kırklareli | 2023 | Eklendi | [İŞKUR raporu](https://media.iskur.gov.tr/94794/kirklareli.pdf) |
| Kocaeli | 2023 | Mevcut şehir verisi | [İŞKUR raporu](https://media.iskur.gov.tr/94796/kocaeli.pdf) |
| Konya | 2023 | Mevcut şehir verisi | [İŞKUR raporu](https://media.iskur.gov.tr/94797/konya.pdf) |
| Kütahya | 2022 | Eklendi | [İŞKUR raporu](https://media.iskur.gov.tr/94798/kutahya.pdf) |
| Tokat | 2022 | Eklendi; Merkez ilçesi | [İŞKUR raporu](https://media.iskur.gov.tr/72023/tokat.pdf) |
| Mersin | 2022 | Mevcut şehir verisi | [İŞKUR raporu](https://media.iskur.gov.tr/94399/mersin.pdf) |
| Niğde | 2022 | Eklendi; Merkez ilçesi | [İŞKUR raporu](https://media.iskur.gov.tr/94342/nigde.pdf) |
| Muğla | 2022 | Eklendi; Menteşe ilçesi | [İŞKUR raporu](https://media.iskur.gov.tr/94803/mugla.pdf) |
| Nevşehir | 2023 | Mevcut şehir verisi | [İŞKUR raporu](https://media.iskur.gov.tr/94341/nevsehir.pdf) |
| Siirt | 2023 | Mevcut şehir verisi | [İŞKUR raporu](https://media.iskur.gov.tr/100474/siirt.pdf) |
| Sivas | 2022 | Mevcut şehir verisi | [İŞKUR raporu](https://media.iskur.gov.tr/94350/sivas.pdf) |
| Şanlıurfa | 2022 | Mevcut şehir verisi | [İŞKUR raporu](https://media.iskur.gov.tr/94419/sanliurfa.pdf) |
| Bartın | 2021 | Eklendi; rapor 2021 TÜİK ADNKS tablosunu içeriyor | [İŞKUR raporu](https://media.iskur.gov.tr/71965/bartin.pdf) |
| Batman | 2022 | Eklendi; Merkez ilçesi | [İŞKUR raporu](https://media.iskur.gov.tr/94375/batman.pdf) |
| Bingöl | 2021 | Eklendi; Merkez ilçesi | [İŞKUR raporu](https://media.iskur.gov.tr/71969/bingol.pdf) |
| Burdur | 2022 | Eklendi; Merkez ilçesi | [İŞKUR raporu](https://media.iskur.gov.tr/94764/burdur.pdf) |
| Kastamonu | 2022 | Eklendi; Merkez ilçesi | [İŞKUR raporu](https://media.iskur.gov.tr/94790/kastamonu.pdf) |
| Manisa | 2025 | Eklendi; Yunusemre ilçesi | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) |
| Bilecik | 2025 | Eklendi; Merkez ilçesi | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) |
| Bolu | 2025 | Eklendi; Merkez ilçesi | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) |
| Çanakkale | 2025 | Eklendi; Merkez ilçesi | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) |
| Çorum | 2025 | Eklendi; Merkez ilçesi | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) |
| Denizli | 2025 | Eklendi; Merkezefendi ilçesi | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) |
| Düzce | 2025 | Eklendi; Merkez ilçesi | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) |
| Edirne | 2025 | Eklendi; Merkez ilçesi | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) |
| Kahramanmaraş | 2025 | Eklendi; Onikişubat ilçesi | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) |
| Kilis | 2025 | Eklendi; Merkez ilçesi | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) |
| Kırşehir | 2025 | Eklendi; Merkez ilçesi | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) |
| Malatya | 2025 | Eklendi; Yeşilyurt ilçesi | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) |
| Mardin | 2025 | Eklendi; Artuklu ilçesi | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) |
| Yozgat | 2025 | Eklendi; Merkez ilçesi | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) |
| Zonguldak | 2025 | Eklendi; Merkez ilçesi | [İlçe yaş grubu sorgusu (TÜİK ADNKS verisi)](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) |

SEGE-2022 ilçe sıralama/skorları, ilgili şehir CSV'lerinde aynı adlandırmayla Bakanlığın [SEGE-2022 ilçe raporuna](https://www.kalkinmakutuphanesi.gov.tr/assets/upload/dosyalar/2022-ilce-sege.pdf) göre kaydedilir.

81 ilin tamamı için 2007–2025 ilçe yaş grubu serisi sunan [DrDataStats sorgusu](https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/) verinin kaynağını TÜİK olarak belirtir. Sorgu aday taraması ve karşılaştırma için kullanılır; şehir eklemesinde seçilen ilçenin 0–14, 15–64 ve 65+ değerleri aynı yılın ilçe toplamıyla karşılaştırılır. Manisa/Yunusemre için 2025 değerleri sırasıyla 56.329, 190.289, 23.737 ve toplam 270.355'tir; Bilecik Merkez için 14.430, 59.960, 8.473 ve 82.863; Bolu Merkez için 38.018, 159.060, 25.511 ve 222.589; Çanakkale Merkez için 31.420, 149.887, 27.306 ve 208.613; Çorum Merkez için 55.428, 205.544, 38.593 ve 299.565; Denizli/Merkezefendi için 71.295, 244.813, 34.977 ve 351.085; Düzce Merkez için 54.185, 185.325, 27.739 ve 267.249; Edirne Merkez için 28.439, 145.612, 26.702 ve 200.753; Kahramanmaraş/Onikişubat için 112.588, 300.352, 34.651 ve 447.591; Kilis Merkez için 35.574, 89.683, 10.173 ve 135.430; Kırşehir Merkez için 30.406, 114.076, 18.886 ve 163.368; Malatya/Yeşilyurt için 68.611, 211.455, 29.824 ve 309.890; Mardin/Artuklu için 60.479, 127.984, 10.255 ve 198.718; Yozgat Merkez için 18.815, 77.576, 12.651 ve 109.042; Zonguldak Merkez için 16.416, 80.421, 18.442 ve 115.279'dur. Her ilçede üç yaş grubunun toplamı nüfusla eşleşir. İlçe SEGE kayıtları Bakanlığın [raporunda](https://www.kalkinmakutuphanesi.gov.tr/assets/upload/dosyalar/2022-ilce-sege.pdf) kontrol edilmiş; tarama bulguları [araştırma notlarında](https://www.sanayi.gov.tr/assets/pdf/birimler/2022-ilce-sege.pdf) karşılaştırılmıştır.

## Kaynakta sorun görülen adaylar

| İl | Tarama bulgusu | Karar |
| --- | --- | --- |
| Bayburt | İŞKUR tablosunda merkez ilçe yaş grupları toplamı nüfus toplamından 50 farklı görünüyor. | Toplamlar düzeltilip doğrulanana kadar eklenmedi. |
| Rize | Aynı raporda yaş tablosu ile ayrı nüfus göstergesi arasında tutarsızlık bulundu. | Aynı referans yılı ve tanım teyit edilene kadar eklenmedi. |
| Samsun | İlçe yaş tablosu bulundu, ancak merkez ilçe hücreleri ve toplam kontrolü tamamlanmadı. | Aday; henüz eklenmedi. |
| Hakkâri | İlçe yaş sayımları var; rapor çalışma çağındaki bandı “15–65” olarak etiketliyor. Şablondaki “15–64” tanımıyla uyumu doğrulanmalı. | Yaş bandı açıklığa kavuşana kadar eklenmedi. |
| Van | İlçe yaş sayımları bulunan rapor 2020 verisini kullanıyor. Daha güncel ve eşleşen yaş tablosu bu turda doğrulanmadı. | Eski veri; eklenmedi. |

## Kalan iller

Aşağıdaki iller için bu tarama turunda şehir eklemeye yetecek, ilçe bazında yaş grubu sayımlarını ve tutarlı toplamları doğrulayan kaynak kaydı oluşturulmadı. Bu, verinin mevcut olmadığı anlamına gelmez; her biri sonraki kaynak taramasında incelenebilir.

İstanbul, Muş, Ordu, Osmaniye, Sakarya, Sinop, Şırnak, Tekirdağ, Trabzon, Tunceli, Uşak, Yalova.

## Doğrulama ölçütü

1. Yaş grubu sayımları kurumsal rapor veya TÜİK tablosunda ilçe bazında bulunmalı.
2. Her ilçe için 0–14 + 15–64 + 65+ toplamı, aynı kaynaktaki genel nüfus toplamına eşit olmalı.
3. `YASLI_ORAN` ve `COCUK_ORAN`, sayımlardan hesaplanmalı; il oranı ilçelere kopyalanmamalı.
4. SEGE-2022 ilçe satırı ve OSM'deki idari ad eşlemesi ayrıca kontrol edilmeli.
5. Rapor yılı ile raporda kullanılan ADNKS veri yılı farklıysa CSV ve adapter notunda veri yılı esas alınmalı.
