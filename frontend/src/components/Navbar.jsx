export default function Navbar() {
  return (
    <header className="h-14 bg-white border-b border-gray-200 flex items-center px-6 shrink-0">
      <h1 className="text-lg font-semibold text-gray-800">ERP System</h1>
      <span className="ml-3 text-xs text-gray-400 hidden sm:inline">
        Satis, urun ve fatura yonetimi
      </span>
    </header>
  );
}
