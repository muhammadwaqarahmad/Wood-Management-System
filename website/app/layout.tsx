import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";
import { LangProvider } from "@/lib/i18n";
import { ToastProvider } from "@/lib/toast";

export const metadata: Metadata = {
  title: "Abdul Sattar Woods",
  description: "Timber trading management — web app over the shared API.",
};

// Apply the saved theme before first paint so there's no light/dark flash.
const noFlash = `try{var t=localStorage.getItem('asw_theme');if(t&&t!=='system')document.documentElement.setAttribute('data-theme',t);var l=localStorage.getItem('asw_lang');if(l){document.documentElement.lang=l;document.documentElement.dir=l==='ur'?'rtl':'ltr';}}catch(e){}`;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: noFlash }} />
      </head>
      <body>
        <AuthProvider>
          <LangProvider>
            <ToastProvider>{children}</ToastProvider>
          </LangProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
