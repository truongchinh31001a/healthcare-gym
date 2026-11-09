export function AdminSection({ title, description }: { title: string; description: string }) {
  return <section><h1>{title}</h1><p>{description}</p>
    <div className="placeholder">Khung chức năng. Chưa kết nối dữ liệu và xử lý nghiệp vụ.</div>
  </section>;
}
