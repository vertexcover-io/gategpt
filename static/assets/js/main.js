export async function getUser() {
  try {
    let response = await fetch("/api/v1/user/profile");
    if (response.ok) {
      let user = await response.json();
      return user;
    }
  } catch (e) {
    console.log(e);
  }
}
