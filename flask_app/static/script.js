function getQueryParam(param) {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get(param);
}

const userId = getQueryParam('user_id');

async function submitRegistration() {
    const selectedSubjects = [];

    document.querySelectorAll('.select-button.selected').forEach(button => {
        const subjectId = button.dataset.subjectId;
        const day = button.dataset.day;
        selectedSubjects.push({ subjectId: subjectId, day: day });
    });

    const responses = await Promise.all(selectedSubjects.map(({ subjectId, day }) =>
        fetch('/register', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                student_id: userId,
                subject_id: subjectId,
                day: day // Передаем день
            })
        })
    ));

    responses.forEach((response, index) => {
        const { subjectId, day } = selectedSubjects[index];
        if (response.ok) {
            console.log(`Регистрация на предмет ${subjectId} в день ${day} успешна!`);
            const button = document.querySelector(`button[data-subject-id="${subjectId}"][data-day="${day}"]`);
            button.innerText = 'Отменить';
            button.onclick = () => unregisterSubject(subjectId, day, button);
        } else {
            console.error(`Ошибка регистрации на предмет ${subjectId} в день ${day}.`);
        }
    });
}

async function registerSubject(subjectId, day, button) {
    console.log("Нажата кнопка для предмета:", subjectId, "в день:", day);

    try {
        const response = await fetch('/register', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                student_id: userId,
                subject_id: subjectId,
                day: day
            })
        });

        if (response.ok) {
            button.innerText = 'Отменить';
            button.onclick = () => unregisterSubject(subjectId, day, button);
            updateButtons(subjectId, 'Отменить');
        }
    } catch (error) {
        console.error("Ошибка при регистрации:", error);
    }
}

async function unregisterSubject(subjectId, day, button) {
    console.log("Нажата кнопка для отмены регистрации предмета:", subjectId);

    try {
        const response = await fetch('/unregister', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                student_id: userId,
                subject_id: subjectId
            })
        });

        if (response.ok) {
            button.innerText = 'Выбрать';
            button.onclick = () => registerSubject(subjectId, day, button);
            updateButtons(subjectId, 'Выбрать');
        }
    } catch (error) {
        console.error("Ошибка при отмене регистрации:", error);
    }
}

function updateButtons(subjectId, text) {
    const buttons = document.querySelectorAll(`button[data-subject-id="${subjectId}"]`);
    buttons.forEach(button => {
        button.innerText = text;
        button.onclick = text === 'Отменить' ?
            () => unregisterSubject(subjectId, button.dataset.day, button) :
            () => registerSubject(subjectId, button.dataset.day, button);
    });
}

document.querySelectorAll('.select-button').forEach(button => {
    button.addEventListener('click', function() {
        this.classList.toggle('selected');
    });
});

document.getElementById('submit-registration-button').addEventListener('click', submitRegistration);
