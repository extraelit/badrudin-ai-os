/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  // Локальный/preview-прокси: браузер обращается к API как к тому же источнику
  // (/__api/...), а Next на сервере перенаправляет запрос на backend внутри
  // контейнера. Это позволяет открыть приложение по одному порту (3000) через
  // Preview, не публикуя отдельно порт backend. Цель задаётся BACKEND_INTERNAL_URL
  // (по умолчанию не задана — тогда rewrite неактивен и обычная сборка не меняется).
  async rewrites() {
    const backend = process.env.BACKEND_INTERNAL_URL;
    if (!backend) return [];
    return [{ source: "/__api/:path*", destination: `${backend}/:path*` }];
  },
};

export default nextConfig;
