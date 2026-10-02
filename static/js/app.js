const routineScrollKey = "olumira.routineScrollY";
const savedScrollY = sessionStorage.getItem(routineScrollKey);

if (savedScrollY !== null) {
	sessionStorage.removeItem(routineScrollKey);
	window.addEventListener("pageshow", () => {
		window.requestAnimationFrame(() => window.scrollTo(0, Number(savedScrollY)));
	}, { once: true });
}

document.querySelectorAll(".task-form").forEach((form) => {
	form.addEventListener("submit", () => {
		sessionStorage.setItem(routineScrollKey, String(window.scrollY));
	});
});

const resourceFilterRoot = document.querySelector(".resource-filter-bar");

if (resourceFilterRoot) {
	const buttons = [...document.querySelectorAll(".resource-filter")];
	const cards = [...document.querySelectorAll(".resource-card")];
	const detailPanel = document.querySelector("#resource-detail-panel");
	const detailCategory = document.querySelector("#resource-detail-category");
	const detailTitle = document.querySelector("#resource-detail-title");
	const detailCopy = document.querySelector("#resource-detail-copy");
	const backButton = document.querySelector("#resource-back-button");

	const showDetail = (category, title, copy) => {
		detailCategory.textContent = category.toUpperCase();
		detailTitle.textContent = title;
		detailCopy.textContent = copy;
		detailPanel.hidden = false;
		detailPanel.scrollIntoView({ behavior: "smooth", block: "start" });
	};

	const hideDetail = () => {
		detailPanel.hidden = true;
	};

	buttons.forEach((button) => {
		button.addEventListener("click", () => {
			const selectedFilter = button.dataset.filter;
			buttons.forEach((item) => item.classList.toggle("active", item === button));
			cards.forEach((card) => {
				const matches = selectedFilter === "All" || card.dataset.category === selectedFilter;
				card.classList.toggle("is-hidden", !matches);
			});
			hideDetail();
		});
	});

	cards.forEach((card) => {
		const openCard = () => showDetail(card.dataset.category, card.dataset.title, card.dataset.copy);
		card.addEventListener("click", openCard);
		card.addEventListener("keydown", (event) => {
			if (event.key === "Enter" || event.key === " ") {
				event.preventDefault();
				openCard();
			}
		});
	});

	document.querySelectorAll(".resource-learn-more").forEach((button) => {
		button.addEventListener("click", (event) => {
			event.stopPropagation();
			showDetail(button.dataset.category, button.dataset.title, button.dataset.copy);
		});
	});

	backButton.addEventListener("click", hideDetail);
}

const communicationRoot = document.querySelector("#communication-app");

if (communicationRoot) {
	const customStorageKey = "olumira.customCommunication.v1";
	const emptyDisplay = communicationRoot.querySelector("#communication-empty");
	const messageDisplay = communicationRoot.querySelector("#communication-message");
	const dialog = communicationRoot.querySelector("#communication-dialog");
	const form = communicationRoot.querySelector("#communication-form");
	let customOptions = [];

	try {
		const storedOptions = JSON.parse(localStorage.getItem(customStorageKey) || "[]");
		if (Array.isArray(storedOptions)) {
			customOptions = storedOptions.filter((option) =>
				option &&
				typeof option.id === "string" &&
				typeof option.name === "string" &&
				typeof option.icon === "string" &&
				typeof option.message === "string" &&
				["Needs", "Activities"].includes(option.category)
			);
		}
	} catch {
		customOptions = [];
	}

	const selectOption = (button) => {
		communicationRoot.querySelectorAll("[data-communication-option]").forEach((optionButton) => {
			const isSelected = optionButton === button;
			optionButton.classList.toggle("selected", isSelected);
			optionButton.setAttribute("aria-pressed", String(isSelected));
		});

		communicationRoot.querySelector("#communication-message-icon").textContent = button.dataset.icon;
		communicationRoot.querySelector("#communication-message-name").textContent = button.dataset.name;
		communicationRoot.querySelector("#communication-message-text").textContent = button.dataset.message;
		emptyDisplay.hidden = true;
		messageDisplay.hidden = false;
	};

	communicationRoot.querySelectorAll("[data-communication-option]").forEach((button) => {
		button.addEventListener("click", () => selectOption(button));
	});

	const addCustomOption = (option) => {
		const category = [...communicationRoot.querySelectorAll(".communication-category")]
			.find((section) => section.dataset.category === option.category);
		if (!category) {
			return;
		}

		const button = document.createElement("button");
		button.type = "button";
		button.className = "communication-option custom-option";
		button.dataset.communicationOption = "";
		button.dataset.id = option.id;
		button.dataset.name = option.name;
		button.dataset.icon = option.icon;
		button.dataset.message = option.message;
		button.dataset.category = option.category;
		button.setAttribute("aria-pressed", "false");

		const icon = document.createElement("span");
		icon.className = "communication-option-icon";
		icon.setAttribute("aria-hidden", "true");
		icon.textContent = option.icon;

		const name = document.createElement("span");
		name.className = "communication-option-name";
		name.textContent = option.name;
		button.append(icon, name);
		button.addEventListener("click", () => selectOption(button));
		category.querySelector(".custom-communication-options").append(button);
	};

	customOptions.forEach(addCustomOption);

	communicationRoot.querySelector("#open-communication-dialog").addEventListener("click", () => {
		dialog.showModal();
		communicationRoot.querySelector("#communication-name").focus();
	});

	const closeDialog = () => dialog.close();
	communicationRoot.querySelector("#close-communication-dialog").addEventListener("click", closeDialog);
	communicationRoot.querySelector("#cancel-communication-dialog").addEventListener("click", closeDialog);

	form.addEventListener("submit", (event) => {
		event.preventDefault();
		const formData = new FormData(form);
		const option = {
			id: `custom-${Date.now()}-${Math.random().toString(36).slice(2)}`,
			name: String(formData.get("name") || "").trim(),
			icon: String(formData.get("icon") || "").trim(),
			message: String(formData.get("message") || "").trim(),
			category: String(formData.get("category") || "Needs"),
		};

		if (!option.name || !option.icon || !option.message) {
			return;
		}

		customOptions.push(option);
		addCustomOption(option);
		try {
			localStorage.setItem(customStorageKey, JSON.stringify(customOptions));
		} catch {
			customOptions.pop();
		}

		const newButton = [...communicationRoot.querySelectorAll("[data-communication-option]")]
			.find((button) => button.dataset.id === option.id);
		if (newButton) {
			selectOption(newButton);
		}
		form.reset();
		dialog.close();
	});
}
