#include "settings_dialog.h"

#include <QFormLayout>
#include <QGroupBox>
#include <QHBoxLayout>
#include <QLabel>
#include <QLineEdit>
#include <QPlainTextEdit>
#include <QPushButton>
#include <QTabWidget>
#include <QVBoxLayout>

#include "api_client.h"

SettingsDialog::SettingsDialog(ApiClient *api, QWidget *parent)
    : QDialog(parent)
    , m_api(api)
{
    setWindowTitle("Settings");
    setModal(true);
    resize(650, 560);
    buildInterface();
}

void SettingsDialog::buildInterface()
{
    setStyleSheet(R"(
        QDialog {
            background: #F7FAFA;
            color: #243434;
        }

        QTabWidget::pane {
            border: 1px solid #D7E5E3;
            border-radius: 10px;
            background: #FFFFFF;
        }

        QTabBar::tab {
            min-width: 120px;
            padding: 10px 16px;

            color: #71817F;
            background: #EFF6F5;

            border: 1px solid #D7E5E3;
        }

        QTabBar::tab:hover {
            background: #E5F3F1;
        }

        QTabBar::tab:selected {
            color: #076D69;
            background: #DDF5F3;
            border-bottom: 2px solid #0ABAB5;
        }

        QLabel {
            color: #344947;
        }

        QLineEdit,
        QPlainTextEdit,
        QComboBox {
            color: #243434;
            background: #FFFFFF;
            border: 1px solid #D3E2E0;
            border-radius: 8px;
            padding: 9px;
            selection-background-color: #B7EAE6;
        }

        QLineEdit:focus,
        QPlainTextEdit:focus,
        QComboBox:focus {
            border: 1px solid #0ABAB5;
        }

        QPushButton {
            min-height: 36px;
            color: #36504E;
            background: #FFFFFF;
            border: 1px solid #D3E2E0;
            border-radius: 8px;
            padding: 0 16px;
        }

        QPushButton:hover {
            color: #076D69;
            background: #EAF7F5;
            border-color: #A9DAD6;
        }

        QPushButton#primaryButton {
            color: white;
            font-weight: 700;
            background: #0ABAB5;
            border-color: #079A96;
        }

        QPushButton#primaryButton:hover {
            background: #079E99;
        }

        QPushButton#dangerButton {
            color: #AA4A4A;
            background: #FFF4F4;
            border-color: #EFCACA;
        }

        QPushButton#dangerButton:hover {
            color: #963E3E;
            background: #FDE8E8;
            border-color: #E5AAAA;
        }
    )");

    auto *root = new QVBoxLayout(this);
    root->setContentsMargins(18, 18, 18, 18);
    root->setSpacing(14);

    auto *title = new QLabel("Application settings", this);
    title->setStyleSheet("font-size:21px; font-weight:700; color:#163C3A;");
    root->addWidget(title);

    auto *tabs = new QTabWidget(this);

    auto *serverPage = new QWidget(tabs);
    auto *serverLayout = new QVBoxLayout(serverPage);
    auto *serverForm = new QFormLayout();

    m_serverUrl = new QLineEdit(m_api->baseUrl(), serverPage);
    serverForm->addRow("Server URL:", m_serverUrl);

    auto *applyButton = new QPushButton("Apply server address", serverPage);
    applyButton->setObjectName("primaryButton");

    serverLayout->addLayout(serverForm);
    serverLayout->addWidget(applyButton);
    serverLayout->addStretch();

    connect(applyButton, &QPushButton::clicked,
            this, &SettingsDialog::applyServerUrl);

    tabs->addTab(serverPage, "Connection");

    auto *agentPage = new QWidget(tabs);
    auto *agentLayout = new QVBoxLayout(agentPage);
    auto *agentForm = new QFormLayout();

    m_agentName = new QLineEdit(agentPage);
    m_agentName->setPlaceholderText("DevOpsAgent");

    m_modelName = new QLineEdit(agentPage);
    m_modelName->setPlaceholderText("Qwen2.5-3B-Instruct");

    m_agentTags = new QLineEdit(agentPage);
    m_agentTags->setPlaceholderText("devops, docker, deploy");

    m_agentPrompt = new QPlainTextEdit(agentPage);
    m_agentPrompt->setPlaceholderText(
        "Ты DevOps-агент. Отвечаешь за инфраструктуру, Docker и CI/CD.");
    m_agentPrompt->setMinimumHeight(150);

    agentForm->addRow("Name:", m_agentName);
    agentForm->addRow("Model folder:", m_modelName);
    agentForm->addRow("Tags:", m_agentTags);
    agentForm->addRow("System prompt:", m_agentPrompt);

    auto *agentButtons = new QHBoxLayout();
    auto *createButton = new QPushButton("Create / update agent", agentPage);
    auto *deleteButton = new QPushButton("Delete agent", agentPage);
    createButton->setObjectName("primaryButton");
    deleteButton->setObjectName("dangerButton");

    agentButtons->addWidget(createButton);
    agentButtons->addWidget(deleteButton);

    agentLayout->addLayout(agentForm);
    agentLayout->addLayout(agentButtons);

    connect(createButton, &QPushButton::clicked,
            this, &SettingsDialog::createAgent);
    connect(deleteButton, &QPushButton::clicked,
            this, &SettingsDialog::deleteAgent);

    tabs->addTab(agentPage, "Agents");

    auto *systemPage = new QWidget(tabs);
    auto *systemLayout = new QVBoxLayout(systemPage);

    auto *metricsButton = new QPushButton("Request runtime metrics", systemPage);
    auto *stateButton = new QPushButton("Request system state", systemPage);
    auto *loggerButton = new QPushButton("Resolve Logger conflicts", systemPage);

    systemLayout->addWidget(metricsButton);
    systemLayout->addWidget(stateButton);
    systemLayout->addWidget(loggerButton);
    systemLayout->addStretch();

    connect(metricsButton, &QPushButton::clicked,
            m_api, &ApiClient::getMetrics);
    connect(stateButton, &QPushButton::clicked,
            m_api, &ApiClient::getSystemState);
    connect(loggerButton, &QPushButton::clicked,
            m_api, &ApiClient::resolveLogger);

    tabs->addTab(systemPage, "System");

    root->addWidget(tabs);

    auto *closeButton = new QPushButton("Close", this);
    connect(closeButton, &QPushButton::clicked, this, &QDialog::accept);
    root->addWidget(closeButton, 0, Qt::AlignRight);
}

void SettingsDialog::applyServerUrl()
{
    m_api->setBaseUrl(m_serverUrl->text());
}

void SettingsDialog::createAgent()
{
    m_api->createAgent(
        m_agentName->text(),
        m_modelName->text(),
        m_agentPrompt->toPlainText(),
        m_agentTags->text().split(',', Qt::SkipEmptyParts));
}

void SettingsDialog::deleteAgent()
{
    const QString name = m_agentName->text().trimmed();
    if (!name.isEmpty()) {
        m_api->deleteAgent(name);
    }
}
