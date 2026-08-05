import { fileURLToPath, URL } from 'node:url'
import path from 'path';
import { defineConfig } from 'vite'
import AutoImport from 'unplugin-auto-import/vite';
import Components from 'unplugin-vue-components/vite';
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'
import viteImagemin from 'vite-plugin-imagemin'
import viteCompression from 'vite-plugin-compression'
import tailwindcss from '@tailwindcss/vite';

const pathSrc = path.resolve(__dirname, 'src');
// https://vite.dev/config/
export default defineConfig({
  base: './',
  plugins: [
    vue(),
    tailwindcss(),
    vueDevTools(),
    AutoImport({
      imports: ['vue'],
      dts: path.resolve(pathSrc, 'auto-imports.d.ts'),
    }),
    Components({
      dts: path.resolve(pathSrc, 'components.d.ts'),
    }),
    viteImagemin({
      gifsicle: {
        optimizationLevel: 3,
        interlaced: false,
      },
      optipng: {
        optimizationLevel: 5,
      },
      mozjpeg: {
        quality: 20,
      },
      pngquant: {
        quality: [0.8, 0.9],
        speed: 4,
      },
      svgo: {
        plugins: [
          {
            name: 'removeViewBox',
          },
          {
            name: 'removeEmptyAttrs',
            active: true,
          },
        ],
      },
    }),
    // viteCompression({
    //   verbose: true,
    //   algorithm: 'gzip',
    //   ext: '.gz',
    //   threshold: 1024,
    //   deleteOriginFile: true
    // })
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    },
  },
  server: {
    watch: {
      ignored: [
        "src_py",
        "memory",
        "resources",
        "tests",
        "docs",
        "others",
        "node_modules",
        "dist",
        "static",
        "public"
      ]
    }
  },
  build: {
    assetsDir: 'assets',
    outDir: 'static',
    rollupOptions: {
      input: {
        main: path.resolve(pathSrc, 'main.ts')
      },
      output: {
        entryFileNames: 'assets/js/[name]-[hash].js',
        chunkFileNames: 'assets/js/[name]-[hash].js',
        assetFileNames: (assetsInfo) => {
          const names = assetsInfo.name?.split('.') || []
          const extname = names[names.length - 1]
          if (extname === "css") {
            return "assets/css/[name]-[hash][extname]"
          } else if (extname === "js") {
            return "assets/js/[name]-[hash][extname]"
          }
          return `assets/[name]-[hash][extname]`
        },
        manualChunks(id) {
          if (id.includes('node_modules')) {
            return id.toString().split('node_modules/')[1].split('/')[0].toString();
          }
        }
      },
    },
    minify: 'terser',
    terserOptions: {
      compress: {
        drop_console: true,
        drop_debugger: true,
      }
    },
  },
})
