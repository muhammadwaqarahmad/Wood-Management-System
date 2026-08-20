import { redirect } from "next/navigation";

// The app lives under the (app) shell; land people on the dashboard, which
// bounces to /login if they're not signed in.
export default function Home() {
  redirect("/dashboard");
}
