let submitButton = document.querySelector("button");

async function postGPTApp(data) {
	try {
		let response = await fetch("/api/v1/custom-gpt-application", {
			method: "POST",
			headers: {
				"Content-Type": "application/json",
			},
			body: JSON.stringify(data),
		});
		if (response.ok) {
			window.location.href = "/";
			return;
		} else if (response.status === 422) {
			let errorJson = (await response.json()).detail[0];
			let error_string = errorJson.loc[1].split("_").join(" ");
			error_string = `${error_string} : ${errorJson.msg}`;
			alert(error_string);
		} else if (response.status === 409) {
			let errorJson = await response.json();
			alert(errorJson.detail);
		}
	} catch (e) {
		console.log(e);
	}
}
submitButton.addEventListener("click", async (e) => {
	e.preventDefault();
	let gptName = document.getElementById("gpt-name").value;
	let gptDescription = document.getElementById("gpt-description").value;
	let gptUrl = document.getElementById("gpt-url").value;
	let verificationMedium = document.getElementById("verification-medium").value;
	await postGPTApp({
		gpt_name: gptName,
		gpt_url: gptUrl,
		gpt_description: gptDescription,
		verification_medium: verificationMedium,
	});
});
