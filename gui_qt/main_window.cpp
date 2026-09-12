#include "main_window.h"

#include <QApplication>
#include <QDragEnterEvent>
#include <QDropEvent>
#include <QEvent>
#include <QFileInfo>
#include <QFrame>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonValue>
#include <QKeyEvent>
#include <QLabel>
#include <QListWidget>
#include <QListWidgetItem>
#include <QMimeData>
#include <QPlainTextEdit>
#include <QPushButton>
#include <QScrollBar>
#include <QSplitter>
#include <QTextCursor>
#include <QTextEdit>
#include <QTimer>
#include <QUrl>
#include <QVBoxLayout>

#include "settings_dialog.h"

namespace
{
constexpr int RequestTimeoutMs = 120000;

QString objectToText(const QJsonObject &object)
{
    return QString::fromUtf8(
        QJsonDocument(object).toJson(QJsonDocument::Indented));
}

QString valueToText(const QJsonValue &value)
{
    if (value.isString()) {
        return value.toString();
    }

    if (value.isObject()) {
        return objectToText(value.toObject());
    }

    if (value.isArray()) {
        return QString::fromUtf8(
            QJsonDocument(value.toArray()).toJson(QJsonDocument::Indented));
    }

    return value.toVariant().toString();
}
}

MainWindow::MainWindow(
    const QString &username,
    const QString &accessToken,
    QWidget *parent)
    : QMainWindow(parent)
    , m_username(username)
{
    m_api.setAccessToken(accessToken);
    setWindowTitle("Multi-Agent Chat");
    setMinimumSize(1100, 720);
    setAcceptDrops(true);

    applyWindowStyle();

    auto *splitter = new QSplitter(Qt::Horizontal, this);
    splitter->setChildrenCollapsible(false);
    splitter->addWidget(buildSidebar());
    splitter->addWidget(buildChatArea());
    splitter->setSizes({270, 1030});
    splitter->setStretchFactor(0, 0);
    splitter->setStretchFactor(1, 1);

    setCentralWidget(splitter);

    connect(
        &m_api,
        &ApiClient::responseReady,
        this,
        &MainWindow::handleResponse);

    connect(
        &m_api,
        &ApiClient::errorOccurred,
        this,
        &MainWindow::handleError);

    m_requestTimeout = new QTimer(this);
    m_requestTimeout->setSingleShot(true);

    connect(m_requestTimeout, &QTimer::timeout, this, [this]() {
        setBusy(false);
        addMessage(
            "System",
            "Сервер не ответил за отведённое время.",
            false,
            true);
    });

    addSystemMessage(
        "Выбран Handler. Напишите запрос или выберите конкретного агента слева.");

    m_api.getAgents();
}

void MainWindow::applyWindowStyle()
{
    setStyleSheet(R"(
        QMainWindow {
            background: #F7FAFA;
        }

        QWidget {
            color: #243434;
        }

        QWidget#sidebar {
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 #F3FAF9,
                stop:1 #ECF6F5);
            border-right: 1px solid #D9E7E5;
        }

        QWidget#chatArea {
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 #FFFFFF,
                stop:1 #F7FAFA);
        }

        QWidget#topBar {
            background: rgba(255, 255, 255, 245);
            border-bottom: 1px solid #DDE9E7;
        }

        QLabel#brand {
            color: #163C3A;
            font-size: 20px;
            font-weight: 700;
        }

        QLabel#sectionLabel {
            color: #819391;
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 1px;
        }

        QLabel#targetLabel {
            color: #203B3A;
            font-size: 16px;
            font-weight: 650;
        }

        QLabel#connectionLabel {
            color: #067D79;
            background: #E6F7F5;
            border: 1px solid #B9E6E2;
            border-radius: 9px;
            padding: 5px 10px;
        }

        QListWidget {
            color: #344947;
            background: transparent;
            border: none;
            outline: none;
            padding: 3px;
        }

        QListWidget::item {
            min-height: 38px;
            margin: 2px 0;
            padding: 0 12px;
            border-radius: 9px;
        }

        QListWidget::item:hover {
            background: #E3F3F1;
        }

        QListWidget::item:selected {
            color: #075E5B;
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 #D2F1EE,
                stop:1 #E8F8F6);
            border-left: 3px solid #0ABAB5;
        }

        QTextEdit#chatDisplay {
            color: #243434;
            background: transparent;
            border: none;
            padding: 24px 11%;
            selection-background-color: #B7EAE6;
        }

        QFrame#composerFrame {
            background: #FFFFFF;
            border: 1px solid #D5E4E2;
            border-radius: 18px;
        }

        QFrame#composerFrame:hover {
            border: 1px solid #B8DAD7;
        }

        QPlainTextEdit#inputArea {
            color: #243434;
            background: transparent;
            border: none;
            padding: 6px;
            selection-background-color: #B7EAE6;
            font-size: 14px;
        }

        QPushButton {
            color: #36504E;
            background: #FFFFFF;
            border: 1px solid #D4E2E0;
            border-radius: 9px;
            padding: 8px 14px;
        }

        QPushButton:hover {
            color: #075E5B;
            background: #EAF7F5;
            border-color: #A9DAD6;
        }

        QPushButton:pressed {
            background: #DDF2F0;
        }

        QPushButton#sendButton {
            min-width: 88px;
            min-height: 38px;

            color: white;
            font-weight: 700;

            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 #0ABAB5,
                stop:1 #079A96);

            border: 1px solid #07928E;
            border-radius: 12px;
        }

        QPushButton#sendButton:hover {
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 #19C8C2,
                stop:1 #088B87);
        }

        QPushButton#sendButton:disabled {
            color: #9AABAA;
            background: #EDF2F1;
            border-color: #DCE6E5;
        }

        QLabel#dropHint {
            color: #879795;
            padding: 5px;
        }

        QSplitter::handle {
            width: 1px;
            background: #D9E7E5;
        }
    )");
}

QWidget *MainWindow::buildSidebar()
{
    auto *sidebar = new QWidget(this);
    sidebar->setObjectName("sidebar");
    sidebar->setMinimumWidth(230);
    sidebar->setMaximumWidth(330);

    auto *layout = new QVBoxLayout(sidebar);
    layout->setContentsMargins(16, 20, 16, 16);
    layout->setSpacing(12);

    auto *brand = new QLabel("MULTI-AGENT", sidebar);
    brand->setObjectName("brand");

    auto *subtitle = new QLabel("Desktop AI workspace", sidebar);
    subtitle->setStyleSheet("color:#819391;");

    auto *newChatButton = new QPushButton("+  New chat", sidebar);
    auto *refreshButton = new QPushButton("Refresh agents", sidebar);

    auto *section = new QLabel("AGENTS", sidebar);
    section->setObjectName("sectionLabel");

    m_agentList = new QListWidget(sidebar);

    auto *handlerItem = new QListWidgetItem("Handler", m_agentList);
    handlerItem->setData(Qt::UserRole, "Handler");
    handlerItem->setSelected(true);

    layout->addWidget(brand);
    layout->addWidget(subtitle);
    layout->addSpacing(8);
    layout->addWidget(newChatButton);
    layout->addSpacing(8);
    layout->addWidget(section);
    layout->addWidget(m_agentList, 1);
    layout->addWidget(refreshButton);

    connect(
        m_agentList,
        &QListWidget::itemClicked,
        this,
        &MainWindow::selectTarget);

    connect(newChatButton, &QPushButton::clicked, this, [this]() {
        m_chatDisplay->clear();
        addSystemMessage("Новый чат начат. Контекст интерфейса очищен.");
    });

    connect(refreshButton, &QPushButton::clicked,
            &m_api, &ApiClient::getAgents);

    return sidebar;
}

QWidget *MainWindow::buildTopBar()
{
    auto *topBar = new QWidget(this);
    topBar->setObjectName("topBar");
    topBar->setFixedHeight(72);

    auto *layout = new QHBoxLayout(topBar);
    layout->setContentsMargins(24, 0, 24, 0);

    auto *titleBox = new QVBoxLayout();
    titleBox->setSpacing(2);

    auto *caption = new QLabel("ACTIVE CONVERSATION", topBar);
    caption->setObjectName("sectionLabel");

    m_targetLabel = new QLabel("Handler", topBar);
    m_targetLabel->setObjectName("targetLabel");

    titleBox->addWidget(caption);
    titleBox->addWidget(m_targetLabel);

    m_connectionLabel =
        new QLabel("API  " + m_api.baseUrl(), topBar);
    m_connectionLabel->setObjectName("connectionLabel");

    auto *userLabel = new QLabel(m_username, topBar);
    userLabel->setStyleSheet("color:#506563; padding:5px 8px;");

    auto *settingsButton =
        new QPushButton("Settings", topBar);
    auto *logoutButton =
        new QPushButton("Logout", topBar);

    layout->addLayout(titleBox);
    layout->addStretch();
    layout->addWidget(m_connectionLabel);
    layout->addWidget(userLabel);
    layout->addWidget(settingsButton);
    layout->addWidget(logoutButton);

    connect(settingsButton, &QPushButton::clicked,
            this, &MainWindow::openSettings);

    connect(logoutButton, &QPushButton::clicked,
            this, &MainWindow::logoutRequested);

    return topBar;
}

QWidget *MainWindow::buildComposer()
{
    auto *container = new QWidget(this);
    auto *outer = new QVBoxLayout(container);
    outer->setContentsMargins(8, 8, 8, 16);
    outer->setSpacing(4);

    auto *frame = new QFrame(container);
    frame->setObjectName("composerFrame");

    auto *layout = new QHBoxLayout(frame);
    layout->setContentsMargins(14, 10, 10, 10);
    layout->setSpacing(10);

    m_inputArea = new QPlainTextEdit(frame);
    m_inputArea->setObjectName("inputArea");
    m_inputArea->setPlaceholderText(
        "Напишите сообщение... Enter — отправить, Shift+Enter — новая строка");
    m_inputArea->setMinimumHeight(56);
    m_inputArea->setMaximumHeight(140);
    m_inputArea->installEventFilter(this);

    m_sendButton = new QPushButton("Send", frame);
    m_sendButton->setObjectName("sendButton");

    layout->addWidget(m_inputArea, 1);
    layout->addWidget(m_sendButton, 0, Qt::AlignBottom);

    m_dropHint = new QLabel(
        "Перетащите документ в окно, чтобы загрузить его на сервер.",
        container);
    m_dropHint->setObjectName("dropHint");

    outer->addWidget(frame);
    outer->addWidget(m_dropHint, 0, Qt::AlignCenter);

    connect(m_sendButton, &QPushButton::clicked,
            this, &MainWindow::sendCurrentMessage);

    return container;
}

QWidget *MainWindow::buildChatArea()
{
    auto *chatArea = new QWidget(this);
    chatArea->setObjectName("chatArea");

    auto *layout = new QVBoxLayout(chatArea);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->setSpacing(0);

    m_chatDisplay = new QTextEdit(chatArea);
    m_chatDisplay->setObjectName("chatDisplay");
    m_chatDisplay->setReadOnly(true);
    m_chatDisplay->setAcceptRichText(true);
    m_chatDisplay->document()->setDefaultStyleSheet(
        "body { font-family:'Segoe UI'; font-size:14px; }");

    layout->addWidget(buildTopBar());
    layout->addWidget(m_chatDisplay, 1);
    layout->addWidget(buildComposer());

    return chatArea;
}

bool MainWindow::eventFilter(QObject *watched, QEvent *event)
{
    if (watched == m_inputArea && event->type() == QEvent::KeyPress) {
        auto *keyEvent = static_cast<QKeyEvent *>(event);

        if ((keyEvent->key() == Qt::Key_Return
             || keyEvent->key() == Qt::Key_Enter)
            && !(keyEvent->modifiers() & Qt::ShiftModifier)) {
            sendCurrentMessage();
            return true;
        }
    }

    return QMainWindow::eventFilter(watched, event);
}

void MainWindow::openSettings()
{
    SettingsDialog dialog(&m_api, this);
    dialog.exec();

    m_connectionLabel->setText("API  " + m_api.baseUrl());
    m_api.getAgents();
}

void MainWindow::sendCurrentMessage()
{
    if (m_requestBusy) {
        return;
    }

    const QString message = m_inputArea->toPlainText().trimmed();
    if (message.isEmpty()) {
        return;
    }

    addMessage("You", message, true);
    m_inputArea->clear();
    setBusy(true);

    if (m_currentTarget == "Handler") {
        m_api.sendHandlerRequest(message);
    } else {
        m_api.runAgent(m_currentTarget, message);
    }

    m_requestTimeout->start(RequestTimeoutMs);
}

void MainWindow::selectTarget(QListWidgetItem *item)
{
    if (!item) {
        return;
    }

    m_currentTarget = item->data(Qt::UserRole).toString();
    if (m_currentTarget.isEmpty()) {
        m_currentTarget = item->text();
    }

    m_targetLabel->setText(m_currentTarget);
    addSystemMessage("Активный собеседник: " + m_currentTarget);
}

void MainWindow::updateAgents(const QJsonObject &json)
{
    const QString previousTarget = m_currentTarget;
    m_agentList->clear();

    auto *handlerItem = new QListWidgetItem("Handler", m_agentList);
    handlerItem->setData(Qt::UserRole, "Handler");

    const QJsonArray agents = json.value("agents").toArray();
    for (const QJsonValue &value : agents) {
        const QString name = value.toString();
        auto *item = new QListWidgetItem(name, m_agentList);
        item->setData(Qt::UserRole, name);
    }

    bool restored = false;
    for (int index = 0; index < m_agentList->count(); ++index) {
        QListWidgetItem *item = m_agentList->item(index);
        if (item->data(Qt::UserRole).toString() == previousTarget) {
            m_agentList->setCurrentItem(item);
            restored = true;
            break;
        }
    }

    if (!restored) {
        m_currentTarget = "Handler";
        m_targetLabel->setText(m_currentTarget);
        m_agentList->setCurrentRow(0);
    }
}

void MainWindow::setBusy(bool busy)
{
    m_requestBusy = busy;
    m_sendButton->setEnabled(!busy);
    m_inputArea->setEnabled(!busy);

    if (busy) {
        m_sendButton->setText("Waiting...");
        m_connectionLabel->setText("PROCESSING");
    } else {
        m_sendButton->setText("Send");
        m_inputArea->setEnabled(true);
        m_inputArea->setFocus();
        m_connectionLabel->setText("API  " + m_api.baseUrl());

        if (m_requestTimeout) {
            m_requestTimeout->stop();
        }
    }
}

void MainWindow::addMessage(
    const QString &sender,
    const QString &message,
    bool userMessage,
    bool errorMessage)
{
    QString safeMessage = message.toHtmlEscaped();
    safeMessage.replace("\n", "<br>");

    const QString senderColor = errorMessage
        ? "#C85C5C"
        : userMessage ? "#078D88" : "#58706E";

    const QString bubbleColor = errorMessage
        ? "#FFF1F1"
        : userMessage ? "#DDF5F3" : "#FFFFFF";

    const QString borderColor = errorMessage
        ? "#F0C5C5"
        : userMessage ? "#A9DDD9" : "#DCE7E5";

    const QString alignment = userMessage ? "right" : "left";
    const QString width = userMessage ? "72%" : "84%";

    const QString html = QString(R"(
        <div style="margin:18px 0; text-align:%1;">
            <div style="
                display:inline-block;
                width:%2;
                text-align:left;
            ">
                <div style="
                    margin:0 6px 7px 6px;
                    color:%3;
                    font-size:12px;
                    font-weight:700;
                ">%4</div>
                <div style="
                    color:#243434;
                    background:%5;
                    border:1px solid %6;
                    border-radius:16px;
                    padding:14px 17px;
                    line-height:1.52;
                ">%7</div>
            </div>
        </div>
    )")
        .arg(alignment)
        .arg(width)
        .arg(senderColor)
        .arg(sender.toHtmlEscaped())
        .arg(bubbleColor)
        .arg(borderColor)
        .arg(safeMessage);

    m_chatDisplay->moveCursor(QTextCursor::End);
    m_chatDisplay->insertHtml(html);
    m_chatDisplay->insertPlainText("\n");

    QScrollBar *bar = m_chatDisplay->verticalScrollBar();
    bar->setValue(bar->maximum());
}

void MainWindow::addSystemMessage(const QString &message)
{
    QString safe = message.toHtmlEscaped();
    safe.replace("\n", "<br>");

    const QString html = QString(R"(
        <div style="
            text-align:center;
            margin:12px 0;
            color:#879795;
            font-size:12px;
        ">%1</div>
    )").arg(safe);

    m_chatDisplay->moveCursor(QTextCursor::End);
    m_chatDisplay->insertHtml(html);
    m_chatDisplay->insertPlainText("\n");
}

QString MainWindow::responseText(
    const QString &title,
    const QJsonObject &json) const
{
    if (title == "Handler") {
        const QString answer = json.value("final_answer").toString();
        if (!answer.isEmpty()) {
            return answer;
        }
    }

    if (title == "Run Agent") {
        const QJsonValue result = json.value("result");
        if (!result.isUndefined() && !result.isNull()) {
            return valueToText(result);
        }
    }

    if (title == "Upload Document") {
        const QString agent = json.value("agent").toString();
        const QString status = json.value("status").toString();

        if (!agent.isEmpty()) {
            return "Документ обработан агентом " + agent
                + (status.isEmpty() ? "." : ". Status: " + status);
        }
    }

    return objectToText(json);
}

void MainWindow::handleResponse(
    const QString &title,
    const QJsonObject &json)
{
    if (title == "Agents") {
        updateAgents(json);
        return;
    }

    if (title == "Create Agent" || title == "Delete Agent") {
        addSystemMessage(responseText(title, json));
        m_api.getAgents();
        return;
    }

    if (title == "Metrics"
        || title == "System State"
        || title == "Logger"
        || title == "Upload Document"
        || title == "Route Document") {
        addMessage(title, responseText(title, json), false);
        if (title == "Upload Document") {
            m_api.getAgents();
        }
        return;
    }

    setBusy(false);
    addMessage(
        title == "Handler" ? "Handler" : m_currentTarget,
        responseText(title, json),
        false);
}

void MainWindow::handleError(const QString &message)
{
    setBusy(false);
    addMessage("Error", message, false, true);
}

void MainWindow::dragEnterEvent(QDragEnterEvent *event)
{
    if (event->mimeData()->hasUrls()) {
        event->acceptProposedAction();
    }
}

void MainWindow::dropEvent(QDropEvent *event)
{
    const QList<QUrl> urls = event->mimeData()->urls();

    for (const QUrl &url : urls) {
        const QString filePath = url.toLocalFile();
        if (filePath.isEmpty()) {
            continue;
        }

        addSystemMessage(
            "Загрузка документа: " + QFileInfo(filePath).fileName());
        m_api.uploadDocument(filePath);
    }

    event->acceptProposedAction();
}
