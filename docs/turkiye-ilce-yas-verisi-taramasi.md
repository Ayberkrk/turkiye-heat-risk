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
| Mersin | 2022 | Mevcut şehir verisi | [İŞKUR raporu](https://media.iskur.gov.tr/94399/mersin.pdf) |
| Muğla | 2022 | Eklendi; Menteşe ilçesi | [İŞKUR raporu](https://media.iskur.gov.tr/94803/mugla.pdf) |
| Nevşehir | 2023 | Mevcut şehir verisi | [İŞKUR raporu](https://media.iskur.gov.tr/94341/nevsehir.pdf) |
| Siirt | 2023 | Mevcut şehir verisi | [İŞKUR raporu](https://media.iskur.gov.tr/100474/siirt.pdf) |
| Sivas | 2022 | Mevcut şehir verisi | [İŞKUR raporu](https://media.iskur.gov.tr/94350/sivas.pdf) |
| Şanlıurfa | 2022 | Mevcut şehir verisi | [İŞKUR raporu](https://media.iskur.gov.tr/94419/sanliurfa.pdf) |
| Bartın | 2021 | Eklendi; rapor 2021 TÜİK ADNKS tablosunu içeriyor | [İŞKUR raporu](https://media.iskur.gov.tr/71965/bartin.pdf) |
| Burdur | 2022 | Eklendi; Merkez ilçesi | [İŞKUR raporu](https://media.iskur.gov.tr/94764/burdur.pdf) |
| Kastamonu | 2022 | Eklendi; Merkez ilçesi | [İŞKUR raporu](https://media.iskur.gov.tr/94790/kastamonu.pdf) |

SEGE-2022 ilçe sıralama/skorları, ilgili şehir CSV'lerinde aynı adlandırmayla Bakanlığın [SEGE-2022 ilçe raporuna](https://www.kalkinmakutuphanesi.gov.tr/assets/upload/dosyalar/2022-ilce-sege.pdf) göre kaydedilir.

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

Ardahan, Batman, Bilecik, Bingöl, Bolu, Çanakkale, Çorum, Denizli, Düzce, Edirne, İstanbul, Kahramanmaraş, Kilis, Kırşehir, Malatya, Manisa, Mardin, Muş, Niğde, Ordu, Osmaniye, Sakarya, Sinop, Şırnak, Tekirdağ, Tokat, Trabzon, Tunceli, Uşak, Yalova, Yozgat, Zonguldak.

## Doğrulama ölçütü

1. Yaş grubu sayımları kurumsal rapor veya TÜİK tablosunda ilçe bazında bulunmalı.
2. Her ilçe için 0–14 + 15–64 + 65+ toplamı, aynı kaynaktaki genel nüfus toplamına eşit olmalı.
3. `YASLI_ORAN` ve `COCUK_ORAN`, sayımlardan hesaplanmalı; il oranı ilçelere kopyalanmamalı.
4. SEGE-2022 ilçe satırı ve OSM'deki idari ad eşlemesi ayrıca kontrol edilmeli.
5. Rapor yılı ile raporda kullanılan ADNKS veri yılı farklıysa CSV ve adapter notunda veri yılı esas alınmalı.
