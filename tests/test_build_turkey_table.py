import pandas as pd
import pytest

import build_turkey_table


def _write_city(output_dir, city_id, rows):
    folder = output_dir / city_id / "paket"
    folder.mkdir(parents=True)
    pd.DataFrame(rows).to_csv(folder / f"{city_id}_mahalleler.csv", index=False)


def _row(name, ilce, hvi, lst20, lst26, km, guvenilir="Evet"):
    return {"mahalle_adi": name, "ilce_adi": ilce, "sira": 0, "yol_sayisi": 30, "toplam_yol_km": km,
            "hvi_ort_2020": hvi - 1, "hvi_ort_2026": hvi, "lst_ort_2020": lst20, "lst_ort_2026": lst26,
            "ndvi_ort_2026": 0.2, "guvenilir_ortalama": guvenilir}


def test_builds_national_tables_with_city_columns_and_km_weighted_means(tmp_path):
    out = tmp_path / "output"
    _write_city(out, "izmir", [_row("A", "Konak", 80, 40.0, 41.0, 3.0), _row("B", "Buca", 50, 44.0, 44.0, 1.0)])
    _write_city(out, "eskisehir", [_row("C", "Tepebaşı", 70, 35.0, 36.0, 2.0, guvenilir="Hayır")])
    _write_city(out, "olmayan_sehir", [_row("X", "Y", 1, 1.0, 1.0, 1.0)])  # config'i yok: atlanır

    target = build_turkey_table.build(output_dir=out, target=tmp_path / "veri")

    mahalle = pd.read_csv(target / "turkiye_mahalleler.csv")
    assert len(mahalle) == 3 and set(mahalle["sehir_kimligi"]) == {"izmir", "eskisehir"}
    cities = pd.read_csv(target / "turkiye_sehirler.csv").set_index("sehir_kimligi")
    # Yol uzunluğu ağırlıklı: (41*3 + 44*1) / 4 = 41.75; değişim 41.75 - 41.0
    assert cities.loc["izmir", "lst_ort_2026"] == pytest.approx(41.75)
    assert cities.loc["izmir", "lst_degisim"] == pytest.approx(0.75)
    assert cities.loc["izmir", "en_riskli_mahalle"] == "A (Konak)"
    # Güvenilir mahalle yoksa yine de ilk satır gösterilir; tek ilçeli şehir işaretlenir.
    assert cities.loc["eskisehir", "en_riskli_mahalle"] == "C (Tepebaşı)"
    assert bool(cities.loc["eskisehir", "demografi_ilce_ici_sabit"]) is True
    sheets = pd.read_excel(target / "turkiye_isi_riski.xlsx", sheet_name=None)
    assert list(sheets) == ["Okuyun", "Şehirler", "Mahalleler", "Kaynaklar ve lisans"]
    assert sheets["Okuyun"]["Açıklama"].str.contains("şehir içi görelidir").any()


def test_no_packages_is_a_clear_error(tmp_path):
    with pytest.raises(SystemExit, match="veri paketi yok"):
        build_turkey_table.build(output_dir=tmp_path, target=tmp_path / "veri")
