## Ne değişti

<!-- Değişikliği ve nedenini anlat. İlgili issue varsa bağla, ör. "Fixes #12". -->

## Nasıl doğrulandı

<!-- Çalıştırdığın komutlar ve loglardan kısa bir alıntı yeterli. -->

## Kontrol listesi

- [ ] `PYTHONPATH=src python -m pytest tests/ -v` yerelde geçiyor
- [ ] Değişiklik için test eklendi ya da güncellendi
- [ ] Kullanıcıyı etkileyen değişiklik `CHANGELOG.md`'ye eklendi

### Yeni şehir ekleyen PR'lar için

- [ ] `src/core/` altında hiçbir dosya değişmedi
- [ ] `python validate_city.py <sehir>` hatasız tamamlanıyor
- [ ] `python validate_city.py <sehir> --osm-coverage` en az %60 kapsam veriyor
- [ ] Şehir, bbox ve nüfus verisinin kaynağı ile lisansı yukarıda belirtildi
