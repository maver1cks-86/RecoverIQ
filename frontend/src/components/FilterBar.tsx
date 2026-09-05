import { SearchIcon } from "./icons";

interface FilterBarProps { searchPlaceholder: string; filters: { label: string; options: string[] }[] }
export function FilterBar({ searchPlaceholder, filters }: FilterBarProps) {
  return <div className="filter-bar"><label className="search-field"><SearchIcon/><input type="search" placeholder={searchPlaceholder} aria-label={searchPlaceholder}/></label>{filters.map((filter) => <select key={filter.label} aria-label={filter.label} defaultValue=""><option value="">{filter.label}: All</option>{filter.options.map((item) => <option key={item}>{item}</option>)}</select>)}</div>;
}
