export interface CrsOption {
  code: string
  name: string
}

// Справочник СК для выпадающих списков.
// Вынесен в отдельный файл-конфиг — расширение списка не требует правки компонент.
export const CRS_OPTIONS: CrsOption[] = [
  { code: 'EPSG:32637', name: 'UTM zone 37N (WGS 84)' },
  { code: 'EPSG:32636', name: 'UTM zone 36N (WGS 84)' },
  { code: 'EPSG:32638', name: 'UTM zone 38N (WGS 84)' },
  { code: 'EPSG:4326', name: 'WGS 84 (географическая)' },
  { code: 'EPSG:3857', name: 'Web Mercator' },
  { code: 'EPSG:28403', name: 'Pulkovo 1942 / Gauss-Kruger zone 3' },
]